// Offline test for ucl32_format.cpp: runs the real draw/validation code on a
// fake model that holds the native UCL fixture captured in ucl32_probe.log.
#include <stdio.h>
#include <string.h>
#include "../ucl32_format.cpp"
#include "fixture_data.h"

static uint8_t* g_model;
static int g_failures = 0;

#define CHECK(cond, ...) do { if (!(cond)) { ++g_failures; printf("  FAIL: " __VA_ARGS__); printf("\n"); } } while (0)

static uintptr_t ev_addr(uint32_t eid) { return (uintptr_t)g_model + kEvents + (uintptr_t)eid * kEventStride; }

static void reset_model(uint16_t year) {
    memset(g_model + kEvents, 0xFF, (size_t)kEventCapacity * kEventStride);
    *(uint16_t*)(g_model + kCalendar + kCalendarYear) = year;
}

static void put_event(uint32_t eid, uint32_t sub, uint32_t code, uint32_t leg,
                      uint32_t home, uint32_t away, bool played) {
    uintptr_t ev = ev_addr(eid);
    memset((void*)ev, 0, kEventStride);
    *(uint16_t*)ev = (uint16_t)eid;
    *(uint32_t*)(ev + kEvPacked) = sub | (code << 16) | (leg << 28) | (played ? kEvPlayedBit : 0);
    *(uint32_t*)(ev + kEvHome) = home;
    *(uint32_t*)(ev + kEvAway) = away;
}

static void put_group(uint32_t group, uint32_t eid_shift, uint32_t replace_from, uint32_t replace_to) {
    for (const ProbeEvent& p : kProbe) {
        if (p.group != group) continue;
        uint32_t h = p.home == replace_from ? replace_to : p.home;
        uint32_t a = p.away == replace_from ? replace_to : p.away;
        put_event(p.eid + eid_shift, p.sub, p.code, p.leg, h, a, false);
    }
}

static uint32_t log_lines() {
    FILE* f = fopen(kLogName, "rb");
    if (!f) return 0;
    uint32_t n = 0; int c;
    while ((c = fgetc(f)) != EOF) if (c == '\n') ++n;
    fclose(f);
    return n;
}

static void print_log_since(uint32_t from) {
    FILE* f = fopen(kLogName, "rb");
    if (!f) return;
    char line[512]; uint32_t n = 0;
    while (fgets(line, sizeof line, f)) if (n++ >= from) printf("    log> %s", line);
    fclose(f);
}

// Independent checker (does not reuse validate_current).
static uint32_t verify_league(uint32_t eid_shift, bool expect_no_same_country) {
    uint32_t ids[64] = {0}, n = 0;
    uint32_t opp[64][8], nopp[64] = {0}, home[64] = {0}, away[64] = {0};
    uint32_t in_round[64][6];
    memset(in_round, 0, sizeof in_round);
    uint32_t events = 0, same = 0, cross_group = 0;
    for (const ProbeEvent& p : kProbe) {
        uintptr_t ev = ev_addr(p.eid + eid_shift);
        uint32_t packed = rd32(ev + kEvPacked);
        CHECK((packed & 0xFFFF) == p.sub && ((packed >> 16) & 0xFFF) == p.code,
              "eid %u: sub/jornada modificados", p.eid);
        uint32_t side[2] = {team_of(rd32(ev + kEvHome)), team_of(rd32(ev + kEvAway))};
        int idx[2];
        for (int s = 0; s < 2; ++s) {
            uint32_t i = 0;
            for (; i < n; ++i) if (ids[i] == side[s]) break;
            if (i == n) ids[n++] = side[s];
            idx[s] = (int)i;
        }
        ++events;
        home[idx[0]]++; away[idx[1]]++;
        in_round[idx[0]][p.code]++; in_round[idx[1]][p.code]++;
        for (int s = 0; s < 2; ++s) {
            uint32_t other = side[1 - s];
            for (uint32_t k = 0; k < nopp[idx[s]]; ++k)
                CHECK(opp[idx[s]][k] != other, "team %u repite rival %u", side[s], other);
            if (nopp[idx[s]] < 8) opp[idx[s]][nopp[idx[s]]++] = other;
        }
        uint16_t c0 = override_country(side[0]), c1 = override_country(side[1]);
        if (!c0) c0 = static_country(side[0]);
        if (!c1) c1 = static_country(side[1]);
        if (c0 && c0 == c1) ++same;
        // Was this pair in the same native group?
        uint32_t g0 = 0, g1 = 0;
        for (const ProbeEvent& q : kProbe) {
            if (team_of(q.home) == side[0] || team_of(q.away) == side[0]) g0 = q.group;
            if (team_of(q.home) == side[1] || team_of(q.away) == side[1]) g1 = q.group;
        }
        if (g0 != g1) ++cross_group;
    }
    CHECK(events == 96, "eventos=%u", events);
    CHECK(n == 32, "clubes=%u", n);
    for (uint32_t i = 0; i < n; ++i) {
        CHECK(nopp[i] == 6, "team %u tiene %u rivales", ids[i], nopp[i]);
        CHECK(home[i] == 3 && away[i] == 3, "team %u local=%u visitante=%u", ids[i], home[i], away[i]);
        for (int r = 0; r < 6; ++r) CHECK(in_round[i][r] == 1, "team %u juega %u veces en J%d", ids[i], in_round[i][r], r + 1);
    }
    if (expect_no_same_country) CHECK(same == 0, "%u cruces del mismo pais", same);
    printf("  verificado: %u partidos, %u clubes, 6 rivales distintos, 3L/3V, 1 partido por jornada, "
           "%u cruces mismo pais, %u/96 partidos entre clubes de grupos nativos distintos\n",
           events, n, same, cross_group);
    return same;
}

static void print_team(uint32_t team, uint32_t eid_shift) {
    printf("  rivales de t%u:", team);
    for (int r = 0; r < 6; ++r)
        for (const ProbeEvent& p : kProbe) {
            if (p.code != (uint32_t)r) continue;
            uintptr_t ev = ev_addr(p.eid + eid_shift);
            uint32_t h = team_of(rd32(ev + kEvHome)), a = team_of(rd32(ev + kEvAway));
            if (h == team) printf(" J%d:vs t%u(L)", r + 1, a);
            if (a == team) printf(" J%d:@ t%u(V)", r + 1, h);
        }
    printf("\n");
}

int main() {
    InitializeCriticalSection(&g_log_lock); g_log_ready = true;
    DeleteFileA(kLogName);
    g_model = (uint8_t*)VirtualAlloc(NULL, kCalendar + kCalendarYear + 0x100,
                                     MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (!g_model) { printf("VirtualAlloc failed\n"); return 2; }
    for (const RtCountry& c : kRuntime) ucl32_format_set_country(c.team, c.country);

    printf("S1 generacion por grupos (orden real de sub_01343BF0), fixture real con Pafos t9504\n");
    reset_model(2026);
    uint32_t mark = log_lines();
    apply_format_on_model((uintptr_t)g_model);            // llamada de la comp 3 padre: 0 eventos
    for (uint32_t g = 1; g <= 8; ++g) {
        put_group(g, 0, 0, 0);
        apply_format_on_model((uintptr_t)g_model);        // llamada del grupo g
    }
    print_log_since(mark);
    CHECK(log_lines() - mark == 1, "se esperaba 1 linea (APPLIED), hay %u", log_lines() - mark);
    verify_league(0, true);
    print_team(9504, 0);

    printf("S1b llamadas repetidas tras aplicar: sin reescritura ni ruido\n");
    uint8_t snapshot[96][8];
    for (int i = 0; i < 96; ++i) memcpy(snapshot[i], (void*)(ev_addr(kProbe[i].eid) + kEvHome), 8);
    mark = log_lines();
    for (int k = 0; k < 3; ++k) apply_format_on_model((uintptr_t)g_model);
    print_log_since(mark);
    CHECK(log_lines() == mark, "hubo lineas nuevas");
    for (int i = 0; i < 96; ++i)
        CHECK(!memcmp(snapshot[i], (void*)(ev_addr(kProbe[i].eid) + kEvHome), 8), "eid %u cambio", kProbe[i].eid);

    printf("S2 club sin pais (id inventado 61000 en lugar de Pafos)\n");
    reset_model(2027);
    mark = log_lines();
    for (uint32_t g = 1; g <= 8; ++g) {
        put_group(g, 0, 0x09480202, (61000u << 14) | 0x202);
        apply_format_on_model((uintptr_t)g_model);
    }
    print_log_since(mark);
    CHECK(log_lines() - mark == 2, "se esperaban INFO + APPLIED, hay %u", log_lines() - mark);
    verify_league(0, true);

    printf("S3 temporada con un partido jugado: se preserva\n");
    reset_model(2028);
    for (uint32_t g = 1; g <= 8; ++g) put_group(g, 0, 0, 0);
    *(uint32_t*)(ev_addr(kProbe[0].eid) + kEvPacked) |= kEvPlayedBit;
    mark = log_lines();
    apply_format_on_model((uintptr_t)g_model);
    apply_format_on_model((uintptr_t)g_model);
    print_log_since(mark);
    CHECK(log_lines() - mark == 1, "se esperaba 1 linea BLOCKED jugados");
    CHECK(rd32(ev_addr(kProbe[0].eid) + kEvHome) == kProbe[0].home, "se modifico un fixture con resultados");

    printf("S4 restos de otra temporada (108 eventos): una sola linea con el motivo\n");
    reset_model(2029);
    for (uint32_t g = 1; g <= 8; ++g) put_group(g, 0, 0, 0);
    put_group(1, 200, 0, 0);
    mark = log_lines();
    for (int k = 0; k < 3; ++k) apply_format_on_model((uintptr_t)g_model);
    print_log_since(mark);
    CHECK(log_lines() - mark == 1, "se esperaba 1 linea, hay %u", log_lines() - mark);

    uint32_t seen[32], ns = 0;
    for (const ProbeEvent& p : kProbe)
        for (int s = 0; s < 2; ++s) {
            uint32_t t = team_of(s ? p.away : p.home), i = 0;
            for (; i < ns; ++i) if (seen[i] == t) break;
            if (i == ns && ns < 32) seen[ns++] = t;
        }

    printf("S5 caso duro pero posible: 8 clubes de un pais + 6 de otro -> 0 cruces\n");
    reset_model(2030);
    for (uint32_t g = 1; g <= 8; ++g) put_group(g, 0, 0, 0);
    for (uint32_t i = 0; i < 8; ++i) ucl32_format_set_country(seen[i], 17);
    for (uint32_t i = 8; i < 14; ++i) ucl32_format_set_country(seen[i], 18);
    mark = log_lines();
    apply_format_on_model((uintptr_t)g_model);
    print_log_since(mark);
    verify_league(0, true);

    printf("S6 17 clubes del mismo pais: cruces inevitables, pero no bloquea\n");
    reset_model(2031);
    for (uint32_t g = 1; g <= 8; ++g) put_group(g, 0, 0, 0);
    for (uint32_t i = 0; i < 17; ++i) ucl32_format_set_country(seen[i], 17);
    mark = log_lines();
    apply_format_on_model((uintptr_t)g_model);
    print_log_since(mark);
    CHECK(log_lines() - mark == 1, "no se aplico");
    verify_league(0, false);

    printf(g_failures ? "\nRESULTADO: %d fallos\n" : "\nRESULTADO: todo OK\n", g_failures);
    return g_failures ? 1 : 0;
}
