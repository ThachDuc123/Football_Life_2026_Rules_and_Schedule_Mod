// Offline stress test of euro_league.h on a club list (id country coef per line).
#include <stdio.h>
#include <stdlib.h>
#include <windows.h>
#include "../euro_league.h"
using namespace league;

int main(int argc, char** argv) {
    if (argc < 3) return 2;
    FILE* f = fopen(argv[1], "r");
    Club clubs[kClubs];
    int n = 0;
    unsigned id, country; double coef;
    while (n < kClubs && fscanf(f, "%u %u %lf", &id, &country, &coef) == 3) {
        clubs[n].id = id; clubs[n].country = (uint16_t)country; clubs[n].coef = (int32_t)(coef * 1000); ++n;
    }
    fclose(f);
    if (n != kClubs) { printf("need 36 clubs, got %d\n", n); return 3; }
    int seeds = atoi(argv[2]);
    LARGE_INTEGER fq, t0, t1; QueryPerformanceFrequency(&fq);
    double worst = 0, total = 0; int fails = 0, bad = 0, relax[3] = {}, maxatt = 0;
    static Plan p;
    for (int s = 1; s <= seeds; ++s) {
        QueryPerformanceCounter(&t0);
        bool ok = make_plan(clubs, clubs[2].id, 0x1234567u * s + 2026, &p);
        QueryPerformanceCounter(&t1);
        double ms = (t1.QuadPart - t0.QuadPart) * 1000.0 / fq.QuadPart;
        total += ms; if (ms > worst) worst = ms;
        if (!ok) { ++fails; continue; }
        relax[p.relax]++;
        if (p.attempts > maxatt) maxatt = p.attempts;
        bad += check_plan(clubs, p, p.relax);
    }
    printf("seeds %d fails %d violations %d relax0/1/2 %d/%d/%d max attempts %d avg %.1f ms worst %.1f ms\n",
           seeds, fails, bad, relax[0], relax[1], relax[2], maxatt, total / seeds, worst);
    if (argc > 3 && make_plan(clubs, clubs[2].id, 2026, &p)) {
        for (int r = 0; r < kRounds; ++r) {
            printf("MD%d:", r + 1);
            for (int i = 0; i < kMatches; ++i) if (p.m[i].round == r) printf(" %u-%u", clubs[p.m[i].home].id, clubs[p.m[i].away].id);
            printf("\n");
        }
    }
    return fails || bad;
}
