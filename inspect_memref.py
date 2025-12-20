import inspect

from xdsl.dialects import memref

print("memref.StoreOp signature:")
try:
    print(inspect.signature(memref.StoreOp.__init__))
except Exception as e:
    print(e)

print("\nmemref.StoreOp.get signature:")
try:
    if hasattr(memref.StoreOp, "get"):
        print(inspect.signature(memref.StoreOp.get))
    else:
        print("No .get method")
except Exception as e:
    print(e)
