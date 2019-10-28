var descriptions = {
	'incorrect': {
		name: 'Wrong Answer',
		body: 'Your program\'s output was incorrect. Make sure you\'re following the output format and check for logic errors.'
	},
	'timeout': {
		name: 'Time Limit Exceeded',
		body: 'Your program ran out of time. Try optimizing your program; you may need to reconsider your approach.'
	},
	'error': {
		name: 'Error',
		body: 'You may have a compile-time error, a run-time error, or your program may have exhausted the available memory (256MB). Ask an organizer for more detailed information on the nature of the error.'
	},
	'correct': {
		name: 'Correct',
		body: 'Nice job! Your program produced the correct output.'
	}
}

var codes = {
	timeout: 'TLE',
	incorrect: 'WA',
	error: 'ERR'
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
		codes: codes,
		result: null,
		results: [],
		testInfo: null,
		state: state,
		descriptions: descriptions
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
			var reader = new FileReader()
			reader.onload = function (e) {
				this.submission.content = e.target.result
			}.bind(this)
			reader.readAsText(file)
		},
		submit () {
			ws.send(JSON.stringify({'type': 'submit', 'submission': this.submission, 'problem': this.problem.slug}))
			this.$refs.fileInput.value = null
			this.submission.filename = ''
			this.submission.content = ''
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
			password: '',
			division: null
		},
		newProblem: {
			name: '',
			slug: '',
			round: null,
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
			this.newTeam.password = ''
		},
		createProblem () {
			if (this.newProblem.name && this.newProblem.slug) {
				ws.send(JSON.stringify({type: 'create_problem', problem: this.newProblem}))
				this.newProblem.name = ''
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
		else if (data.type === 'admin') navigation.admin = true
		else if (data.type === 'problem') {
			problemPanel.problem.name = data.problem.name
			problemPanel.results = data.problem.results
			if (data.problem.results.length >= 0) {
				problemPanel.result = 0
			}
			state.panel = 'problem'
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
		else if (data.type === 'announcements') {
			announcementsPanel.announcements = data.announcements
		}
	})

	ws.addEventListener('open', function (event) {
		closeModals()
		ws.send(JSON.stringify({'type': 'get_problems'}))
		ws.send(JSON.stringify({'type': 'admin_problems'}))
		ws.send(JSON.stringify({'type': 'admin_teams'}))
		ws.send(JSON.stringify({'type': 'get_announcements'}))
	})

	ws.addEventListener('close', function (event) {
		openModal('disconnectedMessage')
		announcementsPanel.first = true
		if (connectTimeout === -1) connectTimeout = setTimeout(connect, 5000)
	})

}

connect()
