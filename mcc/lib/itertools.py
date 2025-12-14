def count(start=0, step=1):
    while True:
        yield start
        start += step

def cycle(p):
    try:
        len(p)
    except TypeError:
        cache = []
        for i in p:
            yield i
            cache.append(i)
        p = cache
    while p:
        yield from p

def repeat(el, n=None):
    if n is None:
        while True:
            yield el
    else:
        for i in range(n):
            yield el


def chain(*p):
    for i in p:
        yield from i

def chain_from_iterable(its):
    for it in its:
        yield from it

def islice(iterable, start, stop=None, step=1):
    if step <= 0:
        raise ValueError("step must be >= 1")
    it = iter(iterable)
    if stop is None:
        stop = start
        start = 0
    for _ in range(start):
        try:
            next(it)
        except StopIteration:
            return
    while start < stop:
        try:
            yield next(it)
        except StopIteration:
            return
        start += step
        for _ in range(step - 1):
            try:
                next(it)
            except StopIteration:
                return

def tee(iterable, n=2):
    return [iter(iterable)] * n

def accumulate(iterable, func=lambda x, y: x + y):
    it = iter(iterable)
    try:
        acc = next(it)
    except StopIteration:
        return
    yield acc
    for element in it:
        acc = func(acc, element)
        yield acc

def dropwhile(predicate, iterable):
    iterator = iter(iterable)
    for x in iterator:
        if not predicate(x):
            yield x
            break

    for x in iterator:
        yield x

def takewhile(predicate, iterable):
    for x in iterable:
        if not predicate(x):
            break
        yield x