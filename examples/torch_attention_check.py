import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.benchmark as benchmark
from torch.nn.attention import SDPBackend, sdpa_kernel

device = "cuda" if torch.cuda.is_available() else "cpu"
#device = "cpu"

# Example Usage:
# query = torch.randn(2, 3, 8, device=device)
# key = torch.randn(2, 3, 8, device=device)
# value = torch.randn(2, 3, 8, device=device)
# F.scaled_dot_product_attention(query, key, value)

def benchmark_torch_ms(f, *args, **kwargs):
    t0 = benchmark.Timer(
        stmt="f(*args, **kwargs)", globals={"args": args, "kwargs": kwargs, "f": f}
    )
    return t0.blocked_autorange().mean * 1e6


def exec_test(is_enabled, name, val_default):
    ret = None
    if is_enabled:
        try:
            exec_ms = benchmark_torch_ms(F.scaled_dot_product_attention, query, key, value)
            print(f"    {name} exec time: {exec_ms:.3f} ms")
            ret = F.scaled_dot_product_attention(query, key, value)
            # Verify that the outputs are close (they should be, as MATH is a correct implementation)
            if val_default is None:
                print("val_default: None")
            else:
                print("val_default: not None")
            if ret is not None and val_default is not None:
                print("not none, shape: ", ret.shape)
                try:
                    torch.testing.assert_close(ret, val_default)
                    print("Results are mathematically equivalent. The backends work as expected.")
                    for row in ret:
                        print(row)
                except AssertionError as e:
                    print(f"Assertion failed: {e}")
                #if torch.eq(val_default, ret):
                #    print("Outputs are same")
                #else:
                #    print("Outputs are different")
        except RuntimeError as ex:
            print(f"{name} error: {ex}")
    else:
        print(f"{name} not enabled")
    return ret


# Lets define the hyper-parameters of our input
batch_size = 16
num_heads = 16
max_sequence_len = 64
embed_dimension = 128

dtype = torch.float16

query = torch.rand(batch_size,
                   num_heads,
                   max_sequence_len,
                   embed_dimension,
                   device=device,
                   dtype=dtype)
key = torch.rand(batch_size,
                 num_heads,
                 max_sequence_len,
                 embed_dimension,
                 device=device,
                 dtype=dtype)
value = torch.rand(batch_size,
                   num_heads,
                   max_sequence_len,
                   embed_dimension,
                   device=device,
                   dtype=dtype)
F.scaled_dot_product_attention(query, key, value)

val_default = None

name = "SDPBackend.Default"
print("----------")
print(name + " test started")
try:
    is_enabled = torch.backends.cuda.math_sdp_enabled()
    val_default = exec_test(is_enabled, name, None)
    print("not none, shape: ", val_default.shape)
except RuntimeError as ex:
    print(f"{name} error support check failed: {ex}")
print(name + " test done")

with sdpa_kernel(SDPBackend.MATH):
    name = "SDPBackend.MATH"
    print("----------")
    print(name + " test started")
    try:
        is_enabled = torch.backends.cuda.math_sdp_enabled()
        exec_test(is_enabled, name, val_default)
    except RuntimeError as ex:
        print(f"{name} error support check failed: {ex}")
    print(name + " test done")

"""
with sdpa_kernel(SDPBackend.EFFICIENT_ATTENTION):
    name = "SDPBackend.EFFICIENT_ATTENTION"
    print("----------")
    print(name + " test started")
    try:
        is_enabled = torch.backends.cuda.mem_efficient_sdp_enabled()
        exec_test(is_enabled, name, val_default)
    except RuntimeError as ex:
        print(f"{name} error support check failed: {ex}")
    print(name + " test done")
"""

with sdpa_kernel(SDPBackend.FLASH_ATTENTION):
    name = "SDPBackend.FLASH_ATTENTION"
    print("----------")
    print(name + " test started")
    try:
        is_enabled = torch.backends.cuda.flash_sdp_enabled()
        exec_test(is_enabled, name, val_default)
    except RuntimeError as ex:
        print(f"{name} error support check failed: {ex}")
    print(name + " test done")

