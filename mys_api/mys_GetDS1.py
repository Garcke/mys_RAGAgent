import time
import random
from hashlib import md5


lettersAndNumbers = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

salt = "lX8m5VO5at5JG7hR8hzqFwzyL5aB1tYo"

t = int(time.time())
r = "".join(random.choices(lettersAndNumbers, k=6))
main = f"salt={salt}&t={t}&r={r}"
ds = md5(main.encode(encoding="UTF-8")).hexdigest()

final = f"{t},{r},{ds}"  # 最终结果。
print(final)