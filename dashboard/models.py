from django.db import models
from django.contrib.auth import get_user_model

class Division(models.Model):
	name = models.CharField(max_length=64)

	def __str__(self):
		return f"Division ({self.id}): {self.name}"

class Profile(models.Model):
	user = models.OneToOneField(get_user_model(), on_delete=models.CASCADE)
	name = models.TextField(unique=True)
	division = models.ForeignKey(Division, on_delete=models.CASCADE)
	eligible = models.BooleanField(blank=True, null=True)
	members = models.TextField(blank=True)

	def __str__(self):
		return f"Profile ({self.id}): {self.name}"

class Round(models.Model):
	name = models.CharField(max_length=64)
	division = models.ForeignKey(Division, on_delete=models.CASCADE)
	start = models.DateTimeField()
	end = models.DateTimeField()

	def __str__(self):
		return f"Round ({self.id}): {self.name}"

class Announcement(models.Model):
	title = models.CharField(max_length=64)
	content = models.TextField()
	timestamp = models.DateTimeField(auto_now_add=True)

class TestCaseGroup(models.Model):
	name = models.TextField(unique=True)

	def __str__(self):
		return f"TestCaseGroup ({self.id}): {self.name}"

class TestCase(models.Model):
	num = models.IntegerField()
	stdin = models.TextField()
	stdout = models.TextField()
	group = models.ForeignKey(TestCaseGroup, on_delete=models.CASCADE)
	preliminary = models.BooleanField()

	def __str__(self):
		return f"TestCase ({self.id}): {self.group.name} #{self.num}, {'pretest' if self.preliminary else 'test'}"

class Problem(models.Model):
	name = models.CharField(max_length=64)
	slug = models.SlugField(max_length=64, unique=True)
	index = models.IntegerField(default=0)
	rounds = models.ManyToManyField(Round)
	test_case_group = models.ForeignKey(TestCaseGroup, on_delete=models.PROTECT, null=True)
	python_time = models.FloatField()
	java_time = models.FloatField()
	cpp_time = models.FloatField()

	def __str__(self):
		return f"Problem ({self.id}): {self.name}"

class Submission(models.Model):
	code = models.TextField()
	filename = models.TextField()
	language = models.TextField()
	timestamp = models.DateTimeField(auto_now_add=True)
	problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
	user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

class TestCaseResult(models.Model):
	test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE)
	result = models.TextField()
	runtime = models.FloatField()
	stdout = models.TextField(blank=True, null=True)
	stderr = models.TextField(blank=True, null=True)
	submission = models.ForeignKey(Submission, on_delete=models.CASCADE)
