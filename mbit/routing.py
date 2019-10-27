from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from channels.routing import ProtocolTypeRouter, URLRouter, ChannelNameRouter
import dashboard.routing
import dashboard.consumers

application = ProtocolTypeRouter({
	'websocket': AllowedHostsOriginValidator(
		AuthMiddlewareStack(
			URLRouter(
				dashboard.routing.websocket_urlpatterns
			)
		)
	),
	'channel': ChannelNameRouter({
		'grading': dashboard.consumers.GradingWorker
	})
})
