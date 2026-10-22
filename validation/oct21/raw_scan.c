/* Exhaustive definition-only scan for A351015.
 *
 * The binary word 1 0^(v-1) encodes a composition part v.  A maximal run
 * of ell equal parts v has type (v, ell).  rho is the number of distinct
 * types, including multiplicities of occurrences only to maintain rho.
 * No minimum-length, rearrangement, or capacity formula is used.
 *
 * Increment invariant: if k ends in t binary ones, its composition ends
 * in t parts equal to 1.  Remove these.  If an earlier part v remains,
 * then v >= 2: replacing the preceding zero by one shortens that last
 * part to v-1.  Append the new part t+1, encoded by the new one followed
 * by the t zeros.  If nothing remains (k = 2^t-1, including k = 0),
 * append the sole part t+1.  Thus increment_composition changes exactly
 * the composition of k into the composition of k+1.
 *
 * append_part merges equal adjacent values; pop_part and pop_run update
 * the frequency of the affected maximal run types.  The scanner visits
 * each integer, with no interval pruning or skipping.
 *
 * C11, standard library only.  Maximum representable word length is 64.
 * --counts FIRST LAST emits one binary byte rho(k) for each k in order.
 * --scan LAST scans 0..LAST and writes a JSON summary.  LAST must be
 * smaller than UINT64_MAX in scan mode so LAST+1 is representable.
 */

#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    unsigned char value[64];
    unsigned char length[64];
    unsigned int used;
    unsigned int rho;
    uint16_t frequency[65][65];
} Composition;

static void remove_type(Composition *state, unsigned int v, unsigned int ell) {
    assert(v >= 1 && v <= 64 && ell >= 1 && ell <= 64);
    assert(state->frequency[v][ell] != 0);
    if (--state->frequency[v][ell] == 0) {
        assert(state->rho != 0);
        --state->rho;
    }
}

static void add_type(Composition *state, unsigned int v, unsigned int ell) {
    assert(v >= 1 && v <= 64 && ell >= 1 && ell <= 64);
    if (state->frequency[v][ell]++ == 0) {
        ++state->rho;
    }
}

static void pop_run(Composition *state) {
    assert(state->used != 0);
    --state->used;
    remove_type(state, state->value[state->used], state->length[state->used]);
}

static void pop_part(Composition *state) {
    assert(state->used != 0);
    const unsigned int i = state->used - 1;
    const unsigned int v = state->value[i];
    const unsigned int ell = state->length[i];
    remove_type(state, v, ell);
    if (ell == 1) {
        --state->used;
    } else {
        state->length[i] = (unsigned char)(ell - 1);
        add_type(state, v, ell - 1);
    }
}

static void append_part(Composition *state, unsigned int v) {
    assert(v >= 1 && v <= 64);
    if (state->used != 0 && state->value[state->used - 1] == v) {
        const unsigned int i = state->used - 1;
        const unsigned int ell = state->length[i];
        assert(ell < 64);
        remove_type(state, v, ell);
        state->length[i] = (unsigned char)(ell + 1);
        add_type(state, v, ell + 1);
    } else {
        assert(state->used < 64);
        state->value[state->used] = (unsigned char)v;
        state->length[state->used] = 1;
        ++state->used;
        add_type(state, v, 1);
    }
}

static void increment_composition(Composition *state) {
    unsigned int t = 0;
    if (state->used != 0 && state->value[state->used - 1] == 1) {
        t = state->length[state->used - 1];
        pop_run(state);
    }
    if (state->used != 0) {
        const unsigned int v = state->value[state->used - 1];
        assert(v >= 2);
        pop_part(state);
        append_part(state, v - 1);
    }
    /* The caller never increments UINT64_MAX (64 trailing one bits). */
    assert(t < 64);
    append_part(state, t + 1);
}

static void decode_initial(Composition *state, uint64_t value) {
    memset(state, 0, sizeof(*state));
    if (value == 0) {
        return;
    }
    int bit = 63;
    while (((value >> bit) & UINT64_C(1)) == 0) {
        --bit;
    }
    unsigned int part = 0;
    for (; bit >= 0; --bit) {
        if ((value >> bit) & UINT64_C(1)) {
            if (part != 0) {
                append_part(state, part);
            }
            part = 1;
        } else {
            ++part;
        }
    }
    append_part(state, part);
}

static int parse_uint64(const char *text, uint64_t *result) {
    if (*text == '\0') {
        return 0;
    }
    for (const char *p = text; *p != '\0'; ++p) {
        if (*p < '0' || *p > '9') {
            return 0;
        }
    }
    errno = 0;
    char *end = NULL;
    const uintmax_t value = strtoumax(text, &end, 10);
    if (errno == ERANGE || *end != '\0' || value > UINT64_MAX) {
        return 0;
    }
    *result = (uint64_t)value;
    return 1;
}

static int emit_counts(uint64_t first, uint64_t last) {
    Composition state;
    decode_initial(&state, first);
    unsigned char buffer[65536];
    size_t used = 0;
    for (uint64_t k = first;; ++k) {
        assert(state.rho <= 64);
        buffer[used++] = (unsigned char)state.rho;
        if (used == sizeof(buffer)) {
            if (fwrite(buffer, 1, used, stdout) != used) {
                return 1;
            }
            used = 0;
        }
        if (k == last) {
            break;
        }
        increment_composition(&state);
    }
    return (used != 0 && fwrite(buffer, 1, used, stdout) != used) || fflush(stdout) != 0;
}

static int exhaustive_scan(uint64_t last) {
    Composition state;
    decode_initial(&state, 0);
    uint64_t first[65];
    uint64_t histogram[65] = {0};
    for (unsigned int i = 0; i <= 64; ++i) {
        first[i] = UINT64_MAX;
    }
    unsigned int largest = 0;
    uint64_t progress = UINT64_C(100000000);
    for (uint64_t k = 0;; ++k) {
        assert(state.rho <= 64);
        ++histogram[state.rho];
        if (first[state.rho] == UINT64_MAX) {
            first[state.rho] = k;
            if (state.rho > largest) {
                largest = state.rho;
            }
            fprintf(stderr, "first rho=%u at k=%" PRIu64 "\n", state.rho, k);
        }
        if (k == progress) {
            fprintf(stderr, "last_visited=%" PRIu64 " rho=%u\n", k, state.rho);
            if (progress <= UINT64_MAX - UINT64_C(100000000)) {
                progress += UINT64_C(100000000);
            }
        }
        if (k == last) {
            break;
        }
        increment_composition(&state);
    }
    printf("{\n  \"interval_inclusive\": [\"0\", \"%" PRIu64 "\"],\n", last);
    printf("  \"integers_visited\": \"%" PRIu64 "\",\n", last + 1);
    printf("  \"maximum_rho_observed\": %u,\n  \"first_occurrences\": [\n", largest);
    int needs_comma = 0;
    for (unsigned int i = 0; i <= 64; ++i) {
        if (first[i] != UINT64_MAX) {
            printf("%s    {\"n\": %u, \"value\": \"%" PRIu64 "\", \"occurrences\": \"%" PRIu64 "\"}",
                   needs_comma ? ",\n" : "", i, first[i], histogram[i]);
            needs_comma = 1;
        }
    }
    printf("\n  ],\n  \"last_maximal_runs\": [");
    for (unsigned int i = 0; i < state.used; ++i) {
        printf("%s[%u, %u]", i == 0 ? "" : ", ",
               (unsigned int)state.value[i], (unsigned int)state.length[i]);
    }
    printf("]\n}\n");
    return fflush(stdout) != 0 || ferror(stderr);
}

int main(int argc, char **argv) {
    uint64_t first = 0;
    uint64_t last = 0;
    if (argc == 3 && strcmp(argv[1], "--scan") == 0 &&
        parse_uint64(argv[2], &last) && last != UINT64_MAX) {
        return exhaustive_scan(last);
    }
    if (argc == 4 && strcmp(argv[1], "--counts") == 0 &&
        parse_uint64(argv[2], &first) && parse_uint64(argv[3], &last) && first <= last) {
        return emit_counts(first, last);
    }
    fprintf(stderr,
            "Usage: %s --scan LAST (0 <= LAST < UINT64_MAX)\n"
            "       %s --counts FIRST LAST (0 <= FIRST <= LAST <= UINT64_MAX)\n",
            argv[0], argv[0]);
    return 2;
}
