screen -S asgi -d -m gunicorn -b unix:asgi.sock -w 4 -k uvicorn.workers.UvicornWorker mbit.asgi:application
screen -S wsgi -d -m gunicorn -b unix:wsgi.sock -w 4 mbit.wsgi
