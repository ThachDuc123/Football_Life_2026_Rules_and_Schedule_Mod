// Runs euro_core.h on an exported Event table and prints a stable text dump
// that compare.py checks against the Python port.
#include <stdio.h>
#include <stdlib.h>
#include "../euro_core.h"
using namespace euro;

int main(int argc, char** argv) {
    if (argc < 4) { fprintf(stderr, "usage: events.bin year qualified_ids_file\n"); return 2; }
    FILE* f = fopen(argv[1], "rb");
    if (!f) return 2;
    static uint8_t events[kEventStride * kEventCapacity];
    size_t got = fread(events, 1, sizeof(events), f);
    fclose(f);
    if (got != sizeof(events)) return 3;
    uint16_t year = (uint16_t)atoi(argv[2]);
    static Standing rows[kMaxTeams];
    int unplayed = 0;
    int n = league_table(events, kEventCapacity, 3, rows, &unplayed);
    if (argc > 4) {                                     // "id place" lines: world club ranking
        static uint32_t ids[4096], places[4096];
        int nr = 0;
        FILE* rf = fopen(argv[4], "r");
        unsigned id, place;
        if (rf) { while (nr < 4096 && fscanf(rf, "%u %u", &id, &place) == 2) { ids[nr] = id; places[nr] = place; ++nr; } fclose(rf); }
        set_ranks(rows, n, ids, places, nr);
    }
    printf("UCL %d %d\n", n, unplayed);
    int order[kMaxTeams];
    rank_order(rows, n, order);
    uint32_t ids[kMaxTeams];
    for (int p = 0; p < n; ++p) {
        const Standing& s = rows[order[p]];
        ids[p] = s.id;
        printf("RANK %d %u %d %d %d %d %d %d %d %d %d %d %d\n", p + 1, s.id, s.played, s.points,
            s.gf - s.ga, s.gf, s.away_gf, s.wins, s.away_wins, s.opp_points, s.opp_gd, s.opp_gf, s.discipline);
    }
    if (n >= 24) {
        uint32_t seed = draw_seed(year, ids, 24);
        BracketTie ties[8];
        build_bracket(seed, ties);
        printf("SEED %u\n", seed);
        for (int k = 0; k < 8; ++k) printf("TIE %d %d %d %d\n", k, ties[k].seed, ties[k].po_home, ties[k].po_away);
        int perm[32];
        if (n == 32) {
            c41_permutation(ties, 32, perm);
            printf("PERM");
            for (int i = 0; i < 32; ++i) printf(" %d", perm[i]);
            printf("\n");
        }
    }
    uint32_t qualified[64];
    int nq = 0;
    FILE* q = fopen(argv[3], "r");
    if (q) { unsigned v; while (nq < 64 && fscanf(q, "%u", &v) == 1) qualified[nq++] = v; fclose(q); }
    if (nq) {
        Third thirds[64];
        int nt = group_thirds(events, kEventCapacity, 5, qualified, nq, thirds);
        for (int i = 0; i < nt; ++i) printf("THIRD %d %u %d %d %d %d\n", i, thirds[i].id, thirds[i].points, thirds[i].gd, thirds[i].gf, thirds[i].wins);
    }
    return 0;
}
