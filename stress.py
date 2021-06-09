import websockets
import json
import asyncio
import random
from datetime import datetime

uri = "wss://26966ab6da.mbit.live/ws"
j = lambda x: json.loads(x) if type(x) == str else json.dumps(x)

def run(i):
	async def session():
		await asyncio.sleep(random.random()*30)
		while True:
			print('starting', i)
			async with websockets.connect(uri, extra_headers={"Cookie": "csrftoken=e0a72y2Pzqi7BqqDl4sB9OCpzCuKDOUMrm8GzXpDv0obeXfRiANxUUytKsgdhX7M; sessionid=yokdvanlrwqyhtv2jmjz20zkedsgmlzd", "Origin": "https://26966ab6da.mbit.live"}) as s:
				await s.recv()
				await s.recv()
				while True:
					time = datetime.now()
					await s.send(j({"type": "get_announcements"}))
					await s.recv()
					await s.send(j({"type": "get_leaderboard", "division": "Standard"}))
					await s.send(j({"type": "get_problems"}))
					await s.recv()
					await s.recv()
					print(datetime.now() - time)
					await asyncio.sleep(random.random()*30 + 5)
					if random.random() > 0.99: break
					print('looped', i)
	asyncio.get_event_loop().run_until_complete(session())

from multiprocessing import Pool
with Pool(500) as p:
	p.map(run, (i for i in range(500)))
