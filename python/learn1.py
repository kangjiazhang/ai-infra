import asyncio
names = ['Bob','Tom','alice','Jerry','Wendy','Smith']
long_name = [name for name in names if len(name)>3]
for name in long_name:
    print(name)

nums = [i if i%3==0 else i*200 for i in range(30)]
for num in nums:
    print(num)


class Numbers:
    def __iter__(self):
        self.nums = 1
        return self
    def __next__(self):
        x = self.nums
        self.nums += 1
        return x

nums = Numbers()
iter(nums)
print(next(nums))
print(next(nums))
print(next(nums))


def countdown(n):
    while True:
        yield n
        n-=1

generator=countdown(10)
print(next(generator))
print(next(generator))
print(next(generator))

def my_decorator(func):
    def wrapper():
        print("函数执行前")
        func()
        print("函数执行后")
    return wrapper

@my_decorator
def say_hello():
    print("Hello!")

say_hello()


def repeat(num_times):
    def decorator(func):
        def wrapper(*args,**kwargs):
            for _ in range(num_times):
                func(*args,**kwargs)
        return wrapper
    return decorator

@repeat(3)
def greet(name):
    print(f"Hello, {name}!")

greet("Alice")


async def hello():
    await asyncio.sleep(1)
    print("Hello")

asyncio.run(hello())

async def task(name):
    print(f"{name} 开始")
    await asyncio.sleep(2)
    print(f"{name} 结束")

async def main():
    await asyncio.gather(
        task("任务A"),
        task("任务B"),
        task("任务C")
    )

asyncio.run(main())