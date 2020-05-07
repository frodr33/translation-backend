from redis.client import StrictRedis
import time


r = StrictRedis(host="13.92.228.127", port="6379", db=0)
pb = r.pubsub()
pb.subscribe("room101")

while True:
	print("in while")
	for message in pb.listen():
		print(message)
	time.sleep(1)
