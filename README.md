# translation-backend
Backend for a real-time translation chat app

## Set up
1. Download and install [Redis](https://redis.io/topics/quickstart). If configured correctly then the command `redis-server` will start redis
2. Need to have [python3](https://www.python.org/downloads/) installed
3. Clone this repository and enter it
4. Create a python virtual environment with `python3 -m venv venv`.
5. Activate virutal environment with `. venv/bin/activate`
6. Install python requirements `pip3 install -r requirements.txt`
7. Use the command `gunicorn -k flask_sockets.worker -b localhost:5000 main:app` to start the server

If done right, the server will start and will be up and running at http://localhost:5000/

## Usage
When the server has started, you can monitor the logs in your terminal. Since the backend is still flaky and unreliable it may start acting up or having weird behavior. If this happens go to http://localhost:5000/reset which will automatically reset the state of the backend
