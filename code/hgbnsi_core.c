/*
 * hgbnsi_core — line-protocol process for the HGBNSI backend. One command per line on stdin,
 * one answer per line on stdout. Every number is a decimal integer of 10^-18 units, except
 * PARSE, which takes a decimal literal. Pure integer; built with -mgeneral-regs-only.
 *
 *   PING
 *   PARSE <literal>                         -> OK <atomic integer> | ERR <reason>
 *   FORMAT <integer>                        -> OK <decimal literal>
 *   GROUND <grounding bits>                 -> OK 1|0
 *   HOLDS <domain> <mask> <9 values> <conditions>                       -> OK 1|0
 *   ROUND <k> <domain mask>×k <9 values> <conditions>                   -> OK <verified mask> <count> <total> <status>
 *   VALIDATE <len> <spec…>                  -> OK <0 or BadSpec code>
 *   CHECK <len> <spec…> <len> <plan…>       -> OK <reason> <cost>
 *   MERIT <len> <spec…>                     -> OK NONE | OK <plan…>
 *   OPTIMUM <len> <spec…>                   -> OK NONE | OK <cost> <plan…>
 *   SOLVE <seed> <restarts> <len> <spec…>   -> OK NONE <proposals> <raw> <repaired> | OK <cost> <proposals> <raw> <repaired> <plan…>
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "hgbnsi.h"

#define MAXTOK 4096
static char *tok[MAXTOK];
static int ntok, pos;

static int next_num(hg_num *x) { return pos < ntok && hg_parse_num(tok[pos++], x); }
static int next_u256(u256 *x) { return pos < ntok && u256_from_dec(tok[pos++], x); }
static int next_small(long *v, long lo, long hi) {
    hg_num x;
    if (!next_num(&x) || x.ovf || x.v < lo || x.v > hi) return 0;
    *v = (long)x.v; return 1;
}
static void put_wad(wad_t v) { char b[64]; wad_int_to_string(v, b, sizeof b); fputs(b, stdout); }
static void put_u256(u256 v) { char b[80]; u256_to_dec(v, b); fputs(b, stdout); }

/* Reads "<len> <values…>" into s; returns length or -1. */
static long read_list(hg_num *s, long max) {
    long len;
    if (!next_small(&len, 0, max)) return -1;
    for (long i = 0; i < len; i++) if (!next_num(&s[i])) return -1;
    return len;
}

/* Reads and validates a spec; returns n, or -1 malformed, or -(100+code) invalid. */
static long read_spec(hg_num *s, wad_t *w) {
    long len = read_list(s, 3 + 4 * HG_MAX_GENERATORS);
    if (len < 0) return -1;
    int code = hg_validate_spec(s, (size_t)len);
    if (code) return -(100 + code);
    for (long i = 0; i < len; i++) w[i] = s[i].v;
    return (long)s[2].v;
}

static int read_ctx(wad_t c[9], u256 *conditions) {
    for (int i = 0; i < 9; i++) {
        hg_num x;
        if (!next_num(&x)) return -1;
        if (!hg_in_wad_range(x)) return 0;
        c[i] = x.v;
    }
    return next_u256(conditions) ? 1 : -1;
}

static void answer(char *line) {
    ntok = 0; pos = 1;
    for (char *t = strtok(line, " \t\r\n"); t && ntok < MAXTOK; t = strtok(NULL, " \t\r\n")) tok[ntok++] = t;
    if (ntok == 0) return;
    const char *cmd = tok[0];
    static hg_num s[3 + 4 * HG_MAX_GENERATORS], p[MAXTOK];
    static wad_t w[3 + 4 * HG_MAX_GENERATORS], plan[HG_MAX_GENERATORS];

    if (!strcmp(cmd, "PING")) { puts("OK hgbnsi-core 1.0 pure-wad18"); return; }
    if (!strcmp(cmd, "PARSE")) {
        wad_t v; wad_err e = ntok == 2 ? wad_parse(tok[1], &v) : WAD_INVALID_ENCODING;
        if (e != WAD_OK) { printf("ERR %s\n", wad_err_name(e)); return; }
        fputs("OK ", stdout); put_wad(v); putchar('\n'); return;
    }
    if (!strcmp(cmd, "FORMAT")) {
        hg_num x; char b[80];
        if (!next_num(&x) || !hg_in_wad_range(x)) { puts("ERR RANGE"); return; }
        wad_format(x.v, b, sizeof b); printf("OK %s\n", b); return;
    }
    if (!strcmp(cmd, "GROUND")) {
        long g; if (!next_small(&g, 0, 255)) { puts("ERR MALFORMED"); return; }
        printf("OK %d\n", hg_grounding_ok((unsigned)g)); return;
    }
    if (!strcmp(cmd, "HOLDS") || !strcmp(cmd, "ROUND")) {
        long k = 1, dom[64]; u256 mask[64];
        if (!strcmp(cmd, "ROUND") && !next_small(&k, 1, 64)) { puts("ERR MALFORMED"); return; }
        for (long i = 0; i < k; i++) if (!next_small(&dom[i], 0, 4) || !next_u256(&mask[i])) { puts("ERR MALFORMED"); return; }
        wad_t c[9]; u256 cond; int r = read_ctx(c, &cond);
        if (r < 0) { puts("ERR MALFORMED"); return; }
        if (r == 0) { puts("ERR RANGE"); return; }
        if (!strcmp(cmd, "HOLDS")) { printf("OK %d\n", hg_energy_holds((int)dom[0], mask[0], c, cond)); return; }
        uint64_t bits = 0; int count = 0;
        for (long i = 0; i < k; i++) if (hg_energy_holds((int)dom[i], mask[i], c, cond)) { bits |= (uint64_t)1 << i; count++; }
        int st = hg_classify_round(count, (int)k);
        printf("OK %llu %d %ld %s\n", (unsigned long long)bits, count, k,
               st == HG_ROUND_FULL ? "FULL" : st == HG_ROUND_PARTIAL ? "PARTIAL" : "FALLBACK");
        return;
    }
    if (!strcmp(cmd, "VALIDATE")) {
        long len = read_list(s, 3 + 4 * HG_MAX_GENERATORS + 8);
        if (len < 0) { puts("ERR MALFORMED"); return; }
        printf("OK %d\n", hg_validate_spec(s, (size_t)len)); return;
    }
    if (!strcmp(cmd, "CHECK")) {
        long n = read_spec(s, w);
        if (n == -1) { puts("ERR MALFORMED"); return; }
        if (n < 0) { printf("ERR BADSPEC %ld\n", -n - 100); return; }
        long plen = read_list(p, MAXTOK - 200);
        if (plen < 0) { puts("ERR MALFORMED"); return; }
        u256 cost; int reason = hg_check_plan(s, p, (size_t)plen, &cost);
        printf("OK %d ", reason); put_u256(cost); putchar('\n'); return;
    }
    if (!strcmp(cmd, "MERIT") || !strcmp(cmd, "OPTIMUM") || !strcmp(cmd, "SOLVE")) {
        long seed = 0, restarts = 0;
        if (!strcmp(cmd, "SOLVE") && (!next_small(&seed, 0, 1L << 40) || !next_small(&restarts, 1, 1000))) { puts("ERR MALFORMED"); return; }
        long n = read_spec(s, w);
        if (n == -1) { puts("ERR MALFORMED"); return; }
        if (n < 0) { printf("ERR BADSPEC %ld\n", -n - 100); return; }
        u256 cost; int ok; hg_solve_stats st = { 0, 0, 0 };
        if (!strcmp(cmd, "MERIT")) ok = hg_merit_order(w, plan);
        else if (!strcmp(cmd, "OPTIMUM")) ok = hg_exact_optimum(w, plan, &cost);
        else ok = hg_solve(w, (uint64_t)seed, (int)restarts, plan, &cost, &st);
        fputs("OK", stdout);
        if (!ok) fputs(" NONE", stdout);
        else if (strcmp(cmd, "MERIT")) { putchar(' '); put_u256(cost); }
        if (!strcmp(cmd, "SOLVE")) printf(" %d %d %d", st.proposals, st.raw_exact_valid, st.repaired_valid);
        if (ok) for (long i = 0; i < n; i++) { putchar(' '); put_wad(plan[i]); }
        putchar('\n'); return;
    }
    puts("ERR UNKNOWN");
}

int main(void) {
    char *line = NULL; size_t cap = 0;
    while (getline(&line, &cap, stdin) > 0) { answer(line); fflush(stdout); }
    free(line);
    return 0;
}
