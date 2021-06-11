var descriptions = {
	'incorrect': {
		name: 'Wrong Answer',
		body: 'Your program\'s output was incorrect. Make sure you\'re following the output format and check for logic errors.'
	},
	'timeout': {
		name: 'Time Limit Exceeded',
		body: 'Your program ran out of time. Try optimizing your program; you may need to reconsider your approach.'
	},
	'memoryout': {
		name: 'Out Of Memory',
		body: 'Your program exhausted the available memory (256 MB).'
	},
	'error': {
		name: 'Error',
		body: 'You may have a compile-time error or a run-time error. See below for more details.'
	},
	'correct': {
		name: 'Correct',
		body: 'Nice job! Your program produced the correct output.'
	}
}

var codes = {
	timeout: 'TLE',
	incorrect: 'WA',
	error: 'ERR',
	memoryout: 'OOM'
}

var state = {
	panel: 'announcements',
	active: ''
}

var navigation = new Vue({
	el: '#navigation',
	delimiters: ['[[', ']]'],
	data: {
		unread: 0,
		problems: [],
		active: null,
		panel: 'announcements',
		admin: false
	},
	methods: {
		navigate: function (panel, slug) {
			if (this.panel === 'announcements' || panel === 'announcements') this.unread = 0
			this.active = slug
			this.panel = panel
			state.active = slug
			if (panel === 'problem' && problemPanel.problem.slug !== slug) problemPanel.problem.slug = slug
			else state.panel = panel
			if (panel === 'admin') {
				var defaultTabs = {'teams': 'team-info', 'problems': 'problem-submissions'}
				if (slug in defaultTabs) adminPanel.tab = defaultTabs[slug]
			}
		}
	}
})

var announcementsPanel = new Vue({
	el: '#announcements-panel',
	delimiters: ['[[', ']]'],
	data: {
		state: state,
		announcements: [],
		first: true
	},
	watch: {
		'announcements': function () {
			if (!this.first) {
				let audio = new Audio('/static/dashboard/notification.mp3')
				audio.play()
				navigation.unread += 1
			}
			this.first = false
			if (profilePanel.noProfile) navigation.unread = this.announcements.length
		}
	}
})

var leaderboardPanel = new Vue({
	el: '#leaderboard-panel',
	delimiters: ['[[', ']]'],
	data: {
		state: state,
		divisions: [],
		division: null,
		teams: [],
		problems: []
	},
	watch: {
		division: function () {
			this.refresh()
		}
	},
	methods: {
		refresh: function () {
			ws.send(JSON.stringify({'type': 'get_leaderboard', 'division': this.division}))
		}
	}
})

var profilePanel = new Vue({
	el: '#profile-panel',
	delimiters: ['[[', ']]'],
	data: {
		state: state,
		divisions: ['Standard', 'Advanced'],
		teamSize: 4,
		profile: {
			name: '',
			division: null,
			eligible: null,
			members: [
				{
					name: '',
					email: '',
					school: '',
					grade: null
				},
				{
					name: '',
					email: '',
					school: '',
					grade: null
				},
				{
					name: '',
					email: '',
					school: '',
					grade: null
				},
				{
					name: '',
					email: '',
					school: '',
					grade: null
				}
			]
		},
		noProfile: false,
		changed: false,
		unsavedChanges: false,
		nameConflict: false
	},
	methods: {
		saveProfile: function () {
			ws.send(JSON.stringify({'type': 'save_profile', 'division': this.profile.division, 'name': this.profile.name, 'members': this.profile.members.filter(m => m.name || m.email || m.school || m.grade).map(m => Object.assign({}, m, {grade: parseInt(m.grade)}))}))
		},
		blurred: function () {
			if (this.changed) this.unsavedChanges = true
		}
	},
	watch: {
		profile: {
			handler: function () {
				this.changed = true
			},
			deep: true
		}
	}
})

var problemPanel = new Vue({
	el: '#problem-panel',
	delimiters: ['[[', ']]'],
	data: {
		problem: {
			'name': null,
			'slug': null
		},
		submission: {
			filename: '',
			language: 'python',
			content: ''
		},
		submissionEditor: false,
		codes: codes,
		result: null,
		results: [],
		testInfo: null,
		state: state,
		descriptions: descriptions,
		inputDownload: ''
	},
	watch: {
		'problem.slug': function (slug) {
			this.testInfo = null
			ws.send(JSON.stringify({'type': 'get_problem', 'slug': slug}))
		}
	},
	methods: {
		setFile: function (file) {
			var language
			this.submission.filename = file.name || ''
			if (language = {"py": "python", "cpp": "c++", "java": "java"}[file.name.split('.').slice(-1)[0]]) {
				this.submission.language = language
			}
			this.submissionEditor = false
			var reader = new FileReader()
			reader.onload = function (e) {
				this.submission.content = e.target.result
			}.bind(this)
			reader.readAsText(file)
		},
		submit () {
			if (this.submission.content && !this.submission.filename) this.submission.filename = 'submission.'+{"python": "py", "pypy": "py", "c++": "cpp", "java": "java"}[this.submission.language]
			ws.send(JSON.stringify({'type': 'submit', 'submission': this.submission, 'problem': this.problem.slug}))
			this.$refs.fileInput.value = null
			this.submission.filename = ''
			this.submission.content = ''
			this.submissionEditor = false
		},
		setTestCase (tindex) {
			ws.send(JSON.stringify({'type': 'get_test_case', 'case': this.results[this.result].tests[tindex].id}))
			setTimeout(function () {
				this.testInfo = tindex
				this.removeClickForInfo()
			}.bind(this), 10)
			if (this.inputDownload) URL.revokeObjectURL(this.inputDownload)
		},
		openSubmissionEditor () {
			this.submissionEditor = true
			this.submission.filename = ''
		},
		removeClickForInfo () {
			document.getElementsByClassName('clickformoreinfo')[0].style.display = 'none'
		}
	}
})

var adminPanel = new Vue({
	el: '#admin-panel',
	delimiters: ['[[', ']]'],
	data: {
		state: state,
		tab: 'problem-submissions',
		problems: [],
		teams: [],
		results: [],
		divisions: [],
		rounds: [],
		testInfo: null,
		descriptions: descriptions,
		codes: codes,
		test_case_groups: [],
		test_case_group: null,
		problem: 0,
		team: 0,
		newTeam: {
			name: '',
			username: '',
			password: '',
			division: null
		},
		newProblem: {
			name: '',
			slug: '',
			round: null,
			cpp_time: 1,
			java_time: 1,
			python_time: 1
		},
		announcement: {
			title: '',
			content: ''
		}
	},
	computed: {
		preliminary () {
			return this.results.filter(r => r.preliminary)
		},
		notPreliminary () {
			return this.results.filter(r => !r.preliminary)
		}
	},
	watch: {
		team () {
			this.testInfo = null
			this.getResult()
		},
		problem () {
			this.testInfo = null
			this.getResult()
		}
	},
	methods: {
		setTestCases () {
			ws.send(JSON.stringify({type: 'set_test_cases', group: this.test_case_group, problem: this.problems[this.problem].slug}))
		},
		announce () {
			ws.send(JSON.stringify({type: 'announce', title: this.announcement.title, content: this.announcement.content}))
			this.announcement.title = ''
			this.announcement.content = ''
		},
		getResult () {
			ws.send(JSON.stringify({type: 'admin_result', team: this.teams[this.team].name, problem: this.problems[this.problem].slug}))
		},
		grade (team, problem) {
			ws.send(JSON.stringify({type: 'grade', team: this.teams[this.team].name, problem: this.problems[this.problem].slug}))
		},
		createTeam () {
			ws.send(JSON.stringify({type: 'create_team', team: this.newTeam}))
			this.newTeam.name = ''
			this.newTeam.username = ''
			this.newTeam.password = ''
		},
		createProblem () {
			if (this.newProblem.name) {
				this.newProblem.slug = slugify(this.newProblem.name)
				ws.send(JSON.stringify({type: 'create_problem', problem: this.newProblem}))
				this.newProblem.name = ''
				this.newProblem.cpp_time = 1
				this.newProblem.java_time = 1
				this.newProblem.python_time = 1
				this.newProblem.slug = ''
			}
		}
	}
})

var ws
var connectTimeout = -1

function connect () {
	if (connectTimeout !== -1) {
		clearTimeout(connectTimeout)
		connectTimeout = -1
	}

	ws = new WebSocket(((window.location.protocol === "https:") ? "wss://" : "ws://") + window.location.host + "/ws");

	ws.addEventListener('message', function (event) {
		var data = JSON.parse(event.data)
		if (data.type === 'problems') navigation.problems = data.problems
		else if (data.type === 'profile') {
			profilePanel.noProfile = false
			profilePanel.unsavedChanges = false
			profilePanel.changed = false
			profilePanel.nameConflict = false
			for (let i = 0; i < 4; i++) {
				data.profile.members[i] = Object.assign({}, profilePanel.profile.members[i], data.profile.members[i])
			}
			profilePanel.profile = Object.assign({}, profilePanel.profile, data.profile)
			ws.send(JSON.stringify({'type': 'get_problems'}))
		}
		else if (data.type === 'divisions') {
			leaderboardPanel.divisions = data.divisions
			leaderboardPanel.division = data.divisions[0].name
			profilePanel.divisions = data.divisions
			profilePanel.division = data.divisions[0].id
		}
		else if (data.type === 'leaderboard') {
			data.teams.sort((a, b) => (b.total === a.total && a.latest && b.latest) ? a.latest - b.latest : b.total - a.total)
			leaderboardPanel.teams = data.teams
			leaderboardPanel.problems = data.problems
		}
		else if (data.type === 'admin') {
			navigation.admin = true
			ws.send(JSON.stringify({'type': 'admin_problems'}))
			ws.send(JSON.stringify({'type': 'admin_teams'}))
		}
		else if (data.type === 'no_profile') {
			profilePanel.noProfile = true
			navigation.navigate('profile', null, true)
			navigation.unread = announcementsPanel.announcements.length
		}
		else if (data.type === 'problem') {
			if (navigation.panel === 'problem' && navigation.active === data.problem.slug) {
				problemPanel.problem.name = data.problem.name
				problemPanel.results = data.problem.results
				if (data.problem.results.length >= 0) {
					problemPanel.result = 0
				}
				state.panel = 'problem'
			}
		}
		else if (data.type === 'submitted') {
			var result = data.result
			var tests = []
			for (var i = 0; i < result.tests; i++) {
				tests.push({})
			}
			result.tests = tests
			problemPanel.results.unshift(result)
			problemPanel.result = 0
			problemPanel.testInfo = null
		}
		else if (data.type === 'case_result') {
			if (problemPanel.results.length > problemPanel.result) {
				for (var tindex = 0; tindex < problemPanel.results[problemPanel.result].tests.length; tindex++) {
					if (problemPanel.results[problemPanel.result].tests[tindex].id === data.case.id) {
						Vue.set(problemPanel.results[problemPanel.result].tests, tindex, data.case)
						setTimeout(function () {
							if (this.tindex === problemPanel.testInfo && this.data.case.stdin) {
								var blob = new Blob([data.case.stdin], { type: "text/plain;charset=utf-8" })
								problemPanel.inputDownload = URL.createObjectURL(blob)
							}
						}.bind({ tindex, data }), 100)
					}
				}
			}
		}
		else if (data.type === 'admin_problems') {
			adminPanel.problems = data.problems
			adminPanel.test_case_groups = data.test_case_groups
			if (adminPanel.teams.length && adminPanel.problems.length) adminPanel.getResult()
		}
		else if (data.type === 'admin_teams') {
			adminPanel.teams = data.teams
			adminPanel.divisions = data.divisions
			adminPanel.rounds = data.rounds
			if (adminPanel.teams.length && adminPanel.problems.length) adminPanel.getResult()
		}
		else if (data.type === 'admin_result') {
			adminPanel.results = data.results
		}
		else if (data.type === 'graded') {
			if (state.panel === 'problem' && state.active === data.problem) {
				ws.send(JSON.stringify({'type': 'get_problem', 'slug': data.problem}))
			}
		}
		else if (data.type === 'fully_graded') {
			if (adminPanel.problems[adminPanel.problem].slug === data.problem && adminPanel.teams[adminPanel.team].name === data.team) {
				adminPanel.getResult()
			}
		}
		else if (data.type === 'error') {
			if (data.message === 'team_name_conflict') profilePanel.nameConflict = true
			else alert(data.message)
		}
		else if (data.type === 'announcements') {
			announcementsPanel.announcements = data.announcements
		}
	})

	ws.addEventListener('open', function (event) {
		ws.send(JSON.stringify({'type': 'get_announcements'}))
		closeModals()
	})

	ws.addEventListener('close', function (event) {
		openModal('disconnectedMessage')
		announcementsPanel.first = true
		if (connectTimeout === -1) connectTimeout = setTimeout(connect, 5000)
	})

}

connect()

function slugify (str) {
    str = str.replace(/^\s+|\s+$/g, '')
    str = str.toLowerCase()
    var from = "ÁÄÂÀÃÅČÇĆĎÉĚËÈÊẼĔȆÍÌÎÏŇÑÓÖÒÔÕØŘŔŠŤÚŮÜÙÛÝŸŽáäâàãåčçćďéěëèêẽĕȇíìîïňñóöòôõøðřŕšťúůüùûýÿžþÞĐđßÆa"
    var to = "AAAAAACCCDEEEEEEEEIIIINNOOOOOORRSTUUUUUYYZaaaaaacccdeeeeeeeeiiiinnooooooorrstuuuuuyyzbBDdBAa"
    for (var i = 0, l = from.length; i < l; i++) {
        str = str.replace(new RegExp(from.charAt(i), 'g'), to.charAt(i))
    }
    str = str.replace(/[^a-z0-9 _]/g, '').replace(/\s+/g, '_').replace(/_+/g, '_');
    return str
}