import multiprocessing

bind = "0.0.0.0:8000"
worker_class = "gevent"
workers = multiprocessing.cpu_count() * 2 + 1
worker_connections = 1000
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
