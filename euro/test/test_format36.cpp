// Runs ucl32_format's 36-club generator on a snapshot of the live model
// (snapshot_live.py) placed in a fake model block, then checks every rule
// and the Round/MatchSlot structure the game reads afterwards.
#include "../../ucl32_format.cpp"
#include <stdio.h>
#include <stdlib.h>

static bool load(uintptr_t model, const char* dir, const char* name, uintptr_t off, size_t size) {
    char path[512]; wsprintfA(path, "%s/%s.bin", dir, name);
    FILE* f = fopen(path, "rb");
    if (!f) { printf("cannot open %s\n", path); return false; }
    size_t got = fread((void*)(model + off), 1, size, f); fclose(f);
    if (got != size) printf("%s: %u of %u bytes\n", path, (unsigned)got, (unsigned)size);
    return got == size;
}

int main(int argc, char** argv) {
    InitializeCriticalSection(&g_log_lock); g_log_ready = true;
    size_t span = 0x16705A8 + 16 * 1024 + 0x1000;
    uintptr_t model = (uintptr_t)VirtualAlloc(NULL, span, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    const char* dir = argv[1];
    if (!load(model, dir, "comps", 0xC12E9C, 300 * 0x314) || !load(model, dir, "count", 0xD0BCF4, 4) ||
        !load(model, dir, "rounds", 0xD65F64, 2000 * 0x208) || !load(model, dir, "events", 0xE9FF08, 13000 * 0x254) ||
        !load(model, dir, "calendar", 0x16038A8, 0x6CD00) || !load(model, dir, "ranking", 0x16705A8, 16 * 1024)) {
        printf("snapshot missing\n"); return 2;
    }
    int bad = 0;
    bool check_only = argc > 3 && lstrcmpA(argv[3], "--check") == 0;
    for (int pass = 0; pass < (check_only ? 0 : 2); ++pass)   // second pass must change nothing
        for (uint16_t base = 3; base <= 5; base += 2)
            for (int g = 1; g <= 4; ++g) league36_group(model, (uint16_t)((g << 10) | base));
    for (uint16_t base = 3; base <= 5; base += 2) {
        int played[40000] = {}; int perround[8] = {}; int clubs = 0;
        static int seen[8][131072];
        for (int r = 0; r < 8; ++r) for (int t = 0; t < 131072; ++t) seen[r][t] = 0;
        int events = 0;
        for (uint32_t eid = 0; eid < kEventCapacity; ++eid) {
            uintptr_t e = model + kEvents + (uintptr_t)eid * kEventStride;
            if (rd16(e) != eid || (rd32(e + 4) & 0x3FF) != base) continue;
            ++events;
            uint32_t code = (rd32(e + 4) >> 16) & 0xFFF;
            if (code > 7) { ++bad; continue; }
            perround[code]++;
            uint32_t h = team_of(rd32(e + 0x14)), a = team_of(rd32(e + 0x18));
            if (seen[code][h]++ || seen[code][a]++) ++bad;
            if (!played[h]++) ++clubs;
            if (!played[a]++) ++clubs;
        }
        printf("comp %u: %d events, %d clubs, per round", base, events, clubs);
        for (int r = 0; r < 8; ++r) printf(" %d", perround[r]);
        printf("\n");
        if (events != 144 || clubs != 36) ++bad;
        for (int r = 0; r < 8; ++r) if (perround[r] != 18) ++bad;
        // Round/MatchSlot structure of every group
        for (int g = 1; g <= 4; ++g) {
            uintptr_t grec = find_comp(model, (uint16_t)((g << 10) | base));
            int refs = 0;
            for (int s = 0; s < 58; ++s) {
                int32_t rid = (int32_t)rd32(grec + 0x88 + s * 4);
                if (rid < 0) continue;
                uintptr_t rr = model + kRounds + (uintptr_t)rid * kRoundStride;
                uint32_t code = rd32(rr + 0x204) >> 26, n = rd32(rr + 0x204) & 0x3FFFFFF;
                if ((code == 8) != (n == 0)) ++bad;
                for (uint32_t k = 0; k < n; ++k) {
                    uintptr_t slot = rr + 4 + k * 0x20;
                    uint16_t eid = rd16(slot + 8);
                    uintptr_t e = model + kEvents + (uintptr_t)eid * kEventStride;
                    if (rd16(e) != eid || (rd32(e + 4) & 0xFFFF) != ((g << 10) | base)) ++bad;
                    if (((rd32(e + 4) >> 16) & 0xFFF) != code) ++bad;
                    if (rd32(slot) != rd32(e + 0x14) || rd32(slot + 4) != rd32(e + 0x18)) ++bad;
                    if (rd16(slot + 14) != ((k << 6) | code)) ++bad;
                    ++refs;
                }
            }
            if (refs != 36) { printf("group %d of comp %u references %d events\n", g, base, refs); ++bad; }
        }
    }
    printf("violations %d\n", bad);
    if (!check_only) {
        // Three-season rule: pretend the two previous seasons had exactly this
        // draw, then redraw: no fixture may keep the same home club.
        lstrcpyA(g_history_path, "test_history.txt");
        DeleteFileA("test_history.txt");
        for (uint16_t base = 3; base <= 5; base += 2) {
            League36* L = league36_plan(model, base);
            if (!L) { ++bad; continue; }
            uint32_t club = team_of(rd32(model + kCalendar + kCareerClub));
            uint32_t h[league::kMatches], a[league::kMatches];
            for (int k = 0; k < league::kMatches; ++k) { h[k] = L->clubs[L->plan.m[k].home].id; a[k] = L->clubs[L->plan.m[k].away].id; }
            history_write(club, base, L->year - 1, h, a, league::kMatches);
            history_write(club, base, L->year - 2, h, a, league::kMatches);
            L->valid = false;
            League36* R = league36_plan(model, base);
            int repeats = 0, reversed = 0;
            for (int k = 0; R && k < league::kMatches; ++k) {
                uint32_t rh = R->clubs[R->plan.m[k].home].id, ra = R->clubs[R->plan.m[k].away].id;
                for (int j = 0; j < league::kMatches; ++j) {
                    if (h[j] == rh && a[j] == ra) ++repeats;
                    if (h[j] == ra && a[j] == rh) ++reversed;
                }
            }
            printf("comp %u three-season rule: %s, same home fixture %d, same pairing other way round %d\n",
                   base, R ? "redrawn" : "NO DRAW", repeats, reversed);
            if (!R || repeats) ++bad;
        }
        printf("violations after three-season test %d\n", bad);
    }
    if (argc > 2) {                                      // events after the generator, for the Lua/Python tests
        FILE* f = fopen(argv[2], "wb");
        if (f) { fwrite((const void*)(model + kEvents), 1, (size_t)kEventStride * kEventCapacity, f); fclose(f); }
    }
    return bad != 0;
}
