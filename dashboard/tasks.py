from __future__ import absolute_import

from celery import shared_task
from asgiref.sync import async_to_sync
import redis

from datetime import timedelta
from itertools import cycle
import secrets
import time
import hashlib
import json
import socket
import logging
import os
import collections
import re
import requests

from mbit.celery import app

from .models import Problem, Submission, TestCaseResult, Division, TestCase

from django.utils import timezone
from django.db.models import Prefetch, Count, F
from django.core.exceptions import ObjectDoesNotExist
from django.forms.models import model_to_dict
from django.db import connection

GRADER = os.getenv("GRADER", "https://localhost:8080")
GRADER_SECRET = os.getenv("GRADER_SECRET", "secret")


@shared_task(autoretry_for=(Exception,), max_retries=5, default_retry_delay=20)
def grade(event):
    problem_obj = Problem.objects.get(slug=event["problem"])
    submission = Submission.objects.get(id=event["submission"])
    r = requests.post(
        GRADER + "/" + ("pretest" if event["preliminary"] else "test"),
        json={
            "secret": GRADER_SECRET,
            "lang": submission.language,
            "prog": submission.code,
            "opts": {
                "time": str(
                    int(
                        {
                            "py": problem_obj.python_time,
                            "java": problem_obj.java_time,
                            "cpp": problem_obj.cpp_time,
                        }[submission.language]
                    )
                )
            },
            "prob": problem_obj.test_case_group.name,
        },
    )
    results = r.json()
    TestCaseResult.objects.bulk_create(
        TestCaseResult(
            submission=submission,
            test_case=problem_obj.test_case_group.testcase_set.filter(
                preliminary=event["preliminary"], num=i + 1
            ).get(),
            result="correct"
            if result["type"] == "success"
            else {
                "timeout": "timeout",
                "compile timeout": "ctimeout",
                "runtime error": "error",
                "compile error": "cerror",
                "incorrect output": "incorrect",
            }.get(result["msg"], "error"),
            runtime=result.get("runtime", 0),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
        )
        for (i, result) in enumerate(results)
    )
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if event["preliminary"]:
        async_to_sync(channel_layer.group_send)(
            event["user_group"],
            {
                "type": "graded",
                "problem": event["problem"],
                "submission": event["submission"],
            },
        )
        if all(result["type"] == "success" for result in results):
            grade.apply_async(
                (
                    {
                        "type": "grade",
                        "problem": event["problem"],
                        "submission": event["submission"],
                        "preliminary": False,
                    },
                ),
                queue="grade",
            )
    elif "channel" in event:
        async_to_sync(channel_layer.send)(
            event["channel"],
            {
                "type": "fully_graded",
                "problem": event["problem"],
                "team": submission.user.username,
            },
        )


@shared_task
def get_leaderboard(event):
    try:
        division = Division.objects.get(name=event["division"])
    except ObjectDoesNotExist:
        return
    r = redis.Redis(port=6379, host=os.environ.get("REDIS_HOST", "localhost"))
    cache = r.get("leaderboard-" + event["division"])
    is_preliminary = False
    if cache and not event["staff"]:
        teams = json.loads(cache)["teams"]
        problems = json.loads(cache)["problems"]
    elif not r.get("generating-leaderboard-" + event["division"]) or event["staff"]:
        if not event["staff"]:
            r.setex("generating-leaderboard-" + event["division"], 20, "1")
        teams = []
        problems = []
        rounds = list(division.round_set.filter(start__lte=timezone.now()))
        ordering = ("index", "name") if division.name != "Advanced" else ("name",)
        round_problems = {
            round.id: list(round.problem_set.all().order_by(*ordering).only("name", "id"))
            for round in rounds
        }
        submission_lookup = {}
        latest_lookup = {}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, c.preliminary, COUNT(t.id)
                    FROM dashboard_submission AS s
                    LEFT JOIN dashboard_testcaseresult AS t
                        ON s.id=t.submission_id
                        AND t.result='correct'
                    INNER JOIN dashboard_testcase AS c
                        ON c.id=t.test_case_id
                    GROUP BY s.id, c.preliminary
            """
            )
            for (sid, prelim, n) in cursor:
                submission_lookup[(sid, prelim)] = n
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.problem_id, s.user_id, s.timestamp, s.id
                    FROM dashboard_submission AS s
                    INNER JOIN (
                        SELECT s.problem_id, s.user_id, MAX(s.timestamp) AS timestamp
                            FROM dashboard_submission AS s
                            GROUP BY s.problem_id, s.user_id
                    ) AS o
                        ON s.problem_id=o.problem_id AND s.user_Id=o.user_id AND s.timestamp=o.timestamp
            """
            )
            for (pid, uid, ts, sid) in cursor:
                latest_lookup[(pid, uid)] = (ts, sid)
        for profile in division.profile_set.all():
            team = {"total": 0, "problems": {}}
            team["name"] = profile.name
            team["eligible"] = profile.eligible
            for round in rounds:
                preliminary = (
                    not event["staff"]
                    and round.end >= timezone.now()
                )
                if preliminary:
                    is_preliminary = True
                team["division"] = round.division.name
                for problem in round_problems[round.id]:
                    if problem.name not in problems:
                        problems.append(problem.name)
                    if (problem.id, profile.user.id) in latest_lookup:
                        (timestamp, sid) = latest_lookup[(problem.id, profile.user.id)]
                        prelim_score = submission_lookup.get((sid, True), 0)
                        score = submission_lookup.get((sid, preliminary), 0)
                        if prelim_score == 10:
                            if "latest" in team:
                                team["latest"] = max(
                                    team["latest"], timestamp.timestamp()
                                )
                            else:
                                team["latest"] = timestamp.timestamp()
                        if not preliminary:
                            if prelim_score != 10 or score != 40:
                                score = 0
                            else:
                                score = 1
                        team["problems"][problem.name] = score
                        team["total"] += int(score == 10) if preliminary else score
                    else:
                        team["problems"][problem.name] = "X"
            teams.append(team)
        if not event["staff"]:
            r.setex(
                "leaderboard-" + event["division"],
                10,
                json.dumps({"teams": teams, "problems": problems}),
            )
        if not event["staff"]:
            r.delete("generating-leaderboard-" + event["division"])
    else:
        while True:
            cache = r.get("leaderboard-" + event["division"])
            if cache:
                teams = json.loads(cache)["teams"]
                problems = json.loads(cache)["problems"]
                break
            time.sleep(0.5)
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.send)(
        event["channel"],
        {
            "type": "leaderboard",
            "teams": teams,
            "problems": problems,
            "preliminary": is_preliminary,
        },
    )


@shared_task
def get_problem(event):
    problem_obj = Problem.objects.get(slug=event["slug"])
    problem = model_to_dict(problem_obj, fields=["name", "slug"])
    testcasecount = (
        problem_obj.test_case_group.testcase_set.only("preliminary", "id")
        .filter(preliminary=True)
        .aggregate(tests=Count("id"))["tests"]
        if problem_obj.test_case_group
        else 0
    )
    results = (
        problem_obj.submission_set.filter(user__id=event["user"])
        .order_by("-timestamp")
        .prefetch_related(
            Prefetch(
                "testcaseresult_set",
                to_attr="preliminary_results",
                queryset=TestCaseResult.objects.filter(test_case__preliminary=True)
                .order_by("test_case__num")
                .only("id", "result")
                .annotate(num=F("test_case__num")),
            )
        )
        .all()
        .only("id", "filename", "timestamp", "language")
    )
    problem["results"] = []
    for resultobj in results:
        result = {
            "id": resultobj.id,
            "filename": resultobj.filename,
            "tests": testcasecount,
            "time": int(resultobj.timestamp.timestamp() * 1000),
            "url": "/submission/" + str(resultobj.id) + "/" + resultobj.filename,
            "timelimit": getattr(
                problem_obj,
                resultobj.language.replace("py", "python").replace("+", "p") + "_time",
            ),
        }
        caseresults = resultobj.preliminary_results
        if len(caseresults):
            result["tests"] = list(
                map(
                    lambda r: {"id": r.id, "result": r.result, "num": r.num},
                    caseresults,
                )
            )
        problem["results"].append(result)
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.send)(
        event["channel"], {"type": "problem", "problem": problem}
    )
