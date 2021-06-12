from django.core.exceptions import ObjectDoesNotExist
from dashboard.models import Division
from dashboard.tasks import grade

from django.core.management.base import BaseCommand

class Command(BaseCommand):
        help = 'Rerun system tests that contained OOM (which only occurs when the grader bugs out)'

        def handle(self, **kwargs):
                for d in ('Advanced', 'Standard'):
                        try: division = Division.objects.get(name=d)
                        except ObjectDoesNotExist: return
                        teams = []
                        rounds = division.round_set.all()
                        for profile in division.profile_set.all():
                                team = {}
                                team['name'] = profile.name
                                team['eligible'] = profile.eligible
                                for round in rounds:
                                        team['division'] = round.division.name
                                        for problem in round.problem_set.all().order_by('id').only('name'):
                                                try: submission = problem.submission_set.filter(user=profile.user).latest('timestamp')
                                                except ObjectDoesNotExist: continue
                                                if submission.testcaseresult_set.filter(result='memoryout', test_case__preliminary=False).count():
                                                        print(f"{team} failed")
                                                        submission.testcaseresult_set.filter(test_case__preliminary=False).delete()
                                                        grade.apply_async(args=({
                                                                'type': 'grade',
                                                                'problem': problem.slug,
                                                                'submission': submission.id,
                                                                'preliminary': False
                                                        },), queue='systemtests')
