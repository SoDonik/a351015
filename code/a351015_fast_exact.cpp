// Exact q=8 boundary computation for OEIS A351015, covering n=17,...,20.
// Build with: g++ -O3 -std=c++17 a351015_fast_exact.cpp -o a351015_fast
// The program prints each exact value, binary word, and optimal run-type order.

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using U128 = unsigned __int128;

struct Type {
    int value;
    int multiplicity;
    int cost;
    U128 bits;
};

static constexpr int Q = 8;
static constexpr int MAX_VALUE = 8;
static const U128 UNSET = static_cast<U128>(-1);
static const U128 INFEASIBLE = static_cast<U128>(-2);

static std::vector<Type> types;
static std::vector<U128> memo;
static std::vector<std::uint16_t> used_forced_cost;
static std::uint32_t forced_mask;
static std::uint32_t boundary_mask;
static std::uint32_t mask_count;
static int forced_cost;
static int boundary_needed;

static U128 block_bits(int value, int multiplicity) {
    U128 result = 0;
    const U128 part = static_cast<U128>(1) << (value - 1);
    for (int i = 0; i < multiplicity; ++i) {
        result = (result << value) | part;
    }
    return result;
}

static int boundary_used(std::uint32_t mask) {
    return __builtin_popcount(mask & boundary_mask);
}

static int remaining_length(std::uint32_t mask) {
    return forced_cost - used_forced_cost[mask]
           + (boundary_needed - boundary_used(mask)) * Q;
}

static U128 solve(std::uint32_t mask, int previous_value) {
    const std::size_t index = static_cast<std::size_t>(previous_value) * mask_count + mask;
    U128 &cached = memo[index];
    if (cached != UNSET) {
        return cached;
    }

    const int used_boundary = boundary_used(mask);
    if ((mask & forced_mask) == forced_mask && used_boundary == boundary_needed) {
        return cached = 0;
    }
    if (used_boundary > boundary_needed) {
        return cached = INFEASIBLE;
    }

    U128 best = INFEASIBLE;
    for (std::size_t i = 0; i < types.size(); ++i) {
        const std::uint32_t bit = static_cast<std::uint32_t>(1) << i;
        if ((mask & bit) != 0 || types[i].value == previous_value) {
            continue;
        }
        if ((boundary_mask & bit) != 0 && used_boundary == boundary_needed) {
            continue;
        }

        const std::uint32_t next_mask = mask | bit;
        const U128 tail = solve(next_mask, types[i].value);
        if (tail == INFEASIBLE) {
            continue;
        }
        const int tail_length = remaining_length(next_mask);
        const U128 candidate = (types[i].bits << tail_length) | tail;
        if (best == INFEASIBLE || candidate < best) {
            best = candidate;
        }
    }
    return cached = best;
}

static std::string decimal(U128 value) {
    if (value == 0) {
        return "0";
    }
    std::string result;
    while (value != 0) {
        result.push_back(static_cast<char>('0' + value % 10));
        value /= 10;
    }
    std::reverse(result.begin(), result.end());
    return result;
}

static std::string binary(U128 value, int length) {
    std::string result;
    result.reserve(length);
    for (int i = length - 1; i >= 0; --i) {
        result.push_back(((value >> i) & 1) != 0 ? '1' : '0');
    }
    return result;
}

static std::vector<int> recover(U128 optimum) {
    std::vector<int> order;
    std::uint32_t mask = 0;
    int previous_value = 0;
    while ((mask & forced_mask) != forced_mask || boundary_used(mask) != boundary_needed) {
        const int used_boundary = boundary_used(mask);
        bool found = false;
        for (std::size_t i = 0; i < types.size(); ++i) {
            const std::uint32_t bit = static_cast<std::uint32_t>(1) << i;
            if ((mask & bit) != 0 || types[i].value == previous_value) {
                continue;
            }
            if ((boundary_mask & bit) != 0 && used_boundary == boundary_needed) {
                continue;
            }
            const std::uint32_t next_mask = mask | bit;
            const U128 tail = solve(next_mask, types[i].value);
            if (tail == INFEASIBLE) {
                continue;
            }
            const U128 candidate = (types[i].bits << remaining_length(next_mask)) | tail;
            if (candidate == optimum) {
                order.push_back(static_cast<int>(i));
                mask = next_mask;
                previous_value = types[i].value;
                optimum = tail;
                found = true;
                break;
            }
        }
        if (!found) {
            throw std::runtime_error("failed to recover an optimal ordering");
        }
    }
    return order;
}

static void initialize_types() {
    for (int value = 1; value <= Q; ++value) {
        for (int multiplicity = 1; multiplicity <= Q; ++multiplicity) {
            const int cost = value * multiplicity;
            if (cost < Q) {
                types.push_back({value, multiplicity, cost,
                                 block_bits(value, multiplicity)});
            }
        }
    }
    const std::size_t forced_count = types.size();
    for (int value = 1; value <= Q; ++value) {
        if (Q % value == 0) {
            const int multiplicity = Q / value;
            types.push_back({value, multiplicity, Q,
                             block_bits(value, multiplicity)});
        }
    }

    forced_mask = (static_cast<std::uint32_t>(1) << forced_count) - 1;
    boundary_mask = ((static_cast<std::uint32_t>(1) << types.size()) - 1) ^ forced_mask;
    mask_count = static_cast<std::uint32_t>(1) << types.size();
    forced_cost = 0;
    for (std::size_t i = 0; i < forced_count; ++i) {
        forced_cost += types[i].cost;
    }

    used_forced_cost.assign(mask_count, 0);
    for (std::uint32_t mask = 1; mask < mask_count; ++mask) {
        const std::uint32_t low = mask & (~mask + 1);
        const int index = __builtin_ctz(low);
        used_forced_cost[mask] = used_forced_cost[mask ^ low]
            + (((forced_mask & low) != 0) ? types[index].cost : 0);
    }
}

int main() {
    initialize_types();
    std::cout << "forced_count=" << __builtin_popcount(forced_mask)
              << " forced_cost=" << forced_cost
              << " boundary_count=" << __builtin_popcount(boundary_mask) << '\n';

    for (boundary_needed = 1; boundary_needed <= 4; ++boundary_needed) {
        memo.assign(static_cast<std::size_t>(MAX_VALUE + 1) * mask_count, UNSET);
        const U128 optimum = solve(0, 0);
        if (optimum == INFEASIBLE) {
            std::cout << "n=" << 16 + boundary_needed << " infeasible\n";
            continue;
        }
        const int length = forced_cost + boundary_needed * Q;
        const std::vector<int> order = recover(optimum);

        std::cout << "n=" << 16 + boundary_needed
                  << " length=" << length
                  << " value=" << decimal(optimum) << '\n';
        std::cout << "binary=" << binary(optimum, length) << '\n';
        std::cout << "order=";
        for (int index : order) {
            std::cout << '(' << types[index].value << ','
                      << types[index].multiplicity << ')';
        }
        std::cout << '\n';
    }
    return 0;
}
