import torch
import torch.nn as nn
import torch.nn.functional as F
device = "cuda" if torch.cuda.is_available() else "cpu"

# Example Usage:
query = torch.randn(2, 3, 8, device=device)
key = torch.randn(2, 3, 8, device=device)
value = torch.randn(2, 3, 8, device=device)
F.scaled_dot_product_attention(query, key, value)

# Lets define a helpful benchmarking function:
import torch.utils.benchmark as benchmark
def benchmark_torch_function_in_microseconds(f, *args, **kwargs):
    t0 = benchmark.Timer(
        stmt="f(*args, **kwargs)", globals={"args": args, "kwargs": kwargs, "f": f}
    )
    return t0.blocked_autorange().mean * 1e6

# Lets define the hyper-parameters of our input
batch_size = 32
max_sequence_len = 1024
num_heads = 32
embed_dimension = 32

dtype = torch.float16

query = torch.rand(batch_size, num_heads, max_sequence_len, embed_dimension, device=device, dtype=dtype)
key = torch.rand(batch_size, num_heads, max_sequence_len, embed_dimension, device=device, dtype=dtype)
value = torch.rand(batch_size, num_heads, max_sequence_len, embed_dimension, device=device, dtype=dtype)

print(f"Default implementation exec time: {benchmark_torch_function_in_microseconds(F.scaled_dot_product_attention, query, key, value):.3f} microseconds")

# Lets explore the speed of each of the 3 implementations
from torch.nn.attention import SDPBackend, sdpa_kernel

with sdpa_kernel(SDPBackend.MATH):
    try:
        if not torch.backends.cuda.math_sdp_enabled():
            print("Error, cuda.math_sdp_enabled = False")
        try:
            math_time=benchmark_torch_function_in_microseconds(F.scaled_dot_product_attention, query, key, value)
            print(f"cuda.Math exec time: {math_time:.3f} microseconds")
        except RuntimeError as ex:
            print(f"cuda.Math error: {ex}")
    except RuntimeError as ex:
        print(f"cuda.Math error support check failed: {ex}")

with sdpa_kernel(SDPBackend.EFFICIENT_ATTENTION):
    try:
        if not torch.backends.cuda.mem_efficient_sdp_enabled():
            print("Error, torch.backends.cuda.mem_efficient_sdp_enabled = False")
        try:
            efficient_time = benchmark_torch_function_in_microseconds(F.scaled_dot_product_attention, query, key, value)
            print(f"Efficient Attention exec time: {efficient_time:.3f} microseconds")
        except RuntimeError as ex:
            print(f"Efficient Attention error: {ex}")
    except RuntimeError as ex:
        print(f"Efficient Attention support check failed: {ex}")

with sdpa_kernel(SDPBackend.FLASH_ATTENTION):
    try:
        if not torch.backends.cuda.flash_sdp_enabled():
            print("Error, cuda.flash_sdp_enabled = False")
        try:
            flash_time=benchmark_torch_function_in_microseconds(F.scaled_dot_product_attention, query, key, value)
            print(f"Flash Attention exec time: {flash_time:.3f} microseconds")
        except RuntimeError as ex:
            print(f"Flash Attention error: {ex}")
    except RuntimeError as ex:
        print(f"Flash Attention support check failed: {ex}")
