// euro_core.h -- UEFA club competition rules (2024/25 onwards), pure logic.
//
// No Windows calls and no game addresses: everything works on a copy or a view
// of the native Event table, so the same code runs inside the game (euro_rules.cpp)
// and in the offline tests (test/test_core.cpp). content/ucl_calendar_guard/
// euro_rules.py is a line-by-line Python port; test/compare.py keeps both equal.
//
// Event record (0x254 bytes): +0 u16 id, +4 u32 packed (low 10 bits competition,
// bits 10..15 group, 16..27 round code, 28..29 leg, bit 30 played), +0x14 home
// and +0x18 away (team << 14), +0x1C home goals, +0x1F away goals, 17 home and
// 18 away appearances of 16 bytes from +0x24 and +0x134 (packed word at +12:
// yellow 0x80000, second yellow 0x40000, red 0x100000).
#pragma once
#include <stdint.h>

namespace euro {

const uint32_t kEventStride = 0x254;
const uint32_t kEventCapacity = 13000;
const uint32_t kPlayedBit = 0x40000000;
const int kMaxTeams = 64;
const int kMaxOpponents = 16;
const uint32_t kUnranked = 100000;

inline uint16_t rd16(const uint8_t* p) { return (uint16_t)(p[0] | (p[1] << 8)); }
inline uint32_t rd32(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
inline uint32_t team_of(uint32_t encoded) { return (encoded >> 14) & 0x1FFFF; }

struct Standing {
    uint32_t id;
    uint32_t encoded;
    int group;              // native group of the club's first league event
    int played, points, gf, ga, away_gf, wins, away_wins, draws, losses, discipline;
    uint32_t rank;          // world club ranking of the game (stands for the club coefficient)
    int opp_points, opp_gd, opp_gf;
    int nopp;
    uint32_t opponents[kMaxOpponents];
};

// UEFA disciplinary points: yellow 1, direct red 3, two yellows in a match 3.
inline int card_points(const uint8_t* entry) {
    if (!rd32(entry + 4)) return 0;
    uint32_t packed = rd32(entry + 12);
    if (packed & 0x40000) return 3;
    return ((packed & 0x80000) ? 1 : 0) + ((packed & 0x100000) ? 3 : 0);
}

inline int side_card_points(const uint8_t* ev, uint32_t first, int slots) {
    int total = 0;
    for (int k = 0; k < slots; ++k) total += card_points(ev + first + k * 16);
    return total;
}

inline Standing* standing_for(Standing* rows, int* n, uint32_t id, uint32_t encoded, int group) {
    for (int i = 0; i < *n; ++i) if (rows[i].id == id) return &rows[i];
    if (*n >= kMaxTeams) return 0;
    Standing* s = &rows[(*n)++];
    Standing zero = {};
    *s = zero;
    s->id = id; s->encoded = encoded; s->group = group; s->rank = kUnranked;
    return s;
}

// Single table of every played event whose competition (low 10 bits) is
// `competition`. Returns the number of clubs, or -1 if more than kMaxTeams.
inline int league_table(const uint8_t* events, uint32_t capacity, uint16_t competition,
                        Standing* rows, int* unplayed) {
    int n = 0;
    *unplayed = 0;
    for (uint32_t eid = 0; eid < capacity; ++eid) {
        const uint8_t* ev = events + (uintptr_t)eid * kEventStride;
        if (rd16(ev) != eid) continue;
        uint32_t packed = rd32(ev + 4);
        if ((packed & 0x3FF) != competition) continue;
        int group = (int)((packed & 0xFFFF) >> 10);
        uint32_t he = rd32(ev + 0x14), ae = rd32(ev + 0x18);
        Standing* h = standing_for(rows, &n, team_of(he), he, group);
        Standing* a = standing_for(rows, &n, team_of(ae), ae, group);
        if (!h || !a) return -1;
        if (!(packed & kPlayedBit)) { ++*unplayed; continue; }
        int hg = ev[0x1C], ag = ev[0x1F];
        h->played++; a->played++;
        h->gf += hg; h->ga += ag; a->gf += ag; a->ga += hg;
        a->away_gf += ag;
        if (hg > ag) { h->wins++; h->points += 3; a->losses++; }
        else if (ag > hg) { a->wins++; a->away_wins++; a->points += 3; h->losses++; }
        else { h->draws++; a->draws++; h->points++; a->points++; }
        h->discipline += side_card_points(ev, 0x24, 17);
        a->discipline += side_card_points(ev, 0x134, 18);
        if (h->nopp < kMaxOpponents) h->opponents[h->nopp++] = a->id;
        if (a->nopp < kMaxOpponents) a->opponents[a->nopp++] = h->id;
    }
    for (int i = 0; i < n; ++i) {
        Standing& s = rows[i];
        s.opp_points = s.opp_gd = s.opp_gf = 0;
        for (int k = 0; k < s.nopp; ++k)
            for (int j = 0; j < n; ++j)
                if (rows[j].id == s.opponents[k]) {
                    s.opp_points += rows[j].points;
                    s.opp_gd += rows[j].gf - rows[j].ga;
                    s.opp_gf += rows[j].gf;
                }
    }
    return n;
}

// Club ranking places: ids[i] has place ranks[i] (1 = first; 0 = unranked).
inline void set_ranks(Standing* rows, int n, const uint32_t* ids, const uint32_t* ranks, int nranks) {
    for (int i = 0; i < n; ++i)
        for (int k = 0; k < nranks; ++k)
            if (ids[k] == rows[i].id) { rows[i].rank = ranks[k] ? ranks[k] : kUnranked; break; }
}

// Regulations of the UEFA Champions League / Europa League 2024/25-2026/27,
// Article 18.01 (league phase). The club coefficient, the last criterion, is
// the game's world club ranking (the one that also makes the pots: lower place
// first, set with set_ranks); the team id only keeps the order total.
inline bool ranks_before(const Standing& a, const Standing& b) {
    if (a.points != b.points) return a.points > b.points;
    if (a.gf - a.ga != b.gf - b.ga) return a.gf - a.ga > b.gf - b.ga;
    if (a.gf != b.gf) return a.gf > b.gf;
    if (a.away_gf != b.away_gf) return a.away_gf > b.away_gf;
    if (a.wins != b.wins) return a.wins > b.wins;
    if (a.away_wins != b.away_wins) return a.away_wins > b.away_wins;
    if (a.opp_points != b.opp_points) return a.opp_points > b.opp_points;
    if (a.opp_gd != b.opp_gd) return a.opp_gd > b.opp_gd;
    if (a.opp_gf != b.opp_gf) return a.opp_gf > b.opp_gf;
    if (a.discipline != b.discipline) return a.discipline < b.discipline;
    if (a.rank != b.rank) return a.rank < b.rank;
    return a.id < b.id;
}

inline void rank_order(const Standing* rows, int n, int* order) {
    for (int i = 0; i < n; ++i) order[i] = i;
    for (int i = 1; i < n; ++i) {
        int v = order[i], j = i;
        while (j && ranks_before(rows[v], rows[order[j - 1]])) { order[j] = order[j - 1]; --j; }
        order[j] = v;
    }
}

// Draws are reproducible: the same season and the same 24 clubs always give
// the same bracket, so a reload or a second call never changes it.
inline uint32_t draw_seed(uint16_t year, const uint32_t* ranked_ids, int n) {
    uint32_t seed = 0x5EED2024u ^ year;
    for (int i = 0; i < n; ++i) seed = (seed * 16777619u) ^ ranked_ids[i];
    return seed ? seed : 0x9E3779B9u;
}

inline uint32_t draw_next(uint32_t* state) {
    uint32_t x = *state;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    return *state = x ? x : 0x9E3779B9u;
}

struct BracketTie {
    int seed;       // league position (0-based) of the club that waits in the round of 16
    int po_home;    // position hosting the play-off first leg (17th-24th)
    int po_away;    // position hosting the play-off second leg (9th-16th)
};

// Knockout phase of the 2025/26 regulations, from 24 league positions.
// Play-off sections I..IV: 9/10 v 23/24, 11/12 v 21/22, 13/14 v 19/20,
// 15/16 v 17/18 (seeded side hosts the second leg). Round of 16 sections:
// A 1/2 v IV, B 3/4 v III, C 5/6 v II, D 7/8 v I. Each section sends one tie
// to each half; quarter-finals A v D and B v C, semi-finals inside a half, so
// 1st and 2nd (also 3rd/4th, 5th/6th, 7th/8th) can only meet in the final.
//
// `ties` receives the eight round-of-16 ties in native order: the game pairs
// round-of-16 ties 2j and 2j+1 in quarter-final j, and quarter-finals 2i and
// 2i+1 in semi-final i, so ties 0-3 are the upper half [A, D, B, C].
inline void build_bracket(uint32_t seed, BracketTie* ties) {
    uint32_t st = seed;
    int po_seeded[4][2], po_unseeded[4][2];
    for (int sec = 0; sec < 4; ++sec) {           // I..IV
        int s0 = 8 + 2 * sec, u0 = 22 - 2 * sec;
        bool swap = draw_next(&st) & 1;
        po_seeded[sec][0] = s0;     po_unseeded[sec][0] = swap ? u0 + 1 : u0;
        po_seeded[sec][1] = s0 + 1; po_unseeded[sec][1] = swap ? u0 : u0 + 1;
    }
    BracketTie half[4][2];                          // [A..D][upper, lower]
    for (int x = 0; x < 4; ++x) {
        int sec = 3 - x;                            // A faces IV ... D faces I
        int t = draw_next(&st) & 1;
        BracketTie p0 = {2 * x, po_unseeded[sec][t], po_seeded[sec][t]};
        BracketTie p1 = {2 * x + 1, po_unseeded[sec][1 - t], po_seeded[sec][1 - t]};
        int h = draw_next(&st) & 1;
        half[x][h] = p0;
        half[x][1 - h] = p1;
    }
    static const int kOrder[4] = {0, 3, 1, 2};      // A, D, B, C
    int k = 0;
    for (int h = 0; h < 2; ++h)
        for (int i = 0; i < 4; ++i) ties[k++] = half[kOrder[i]][h];
}

// Native 24-slot vector of ucl32_c41: slot 3k waits, slot 3k+1 hosts the first
// leg of play-off k against slot 3k+2. c41 reads slot 3k from rank index k,
// 3k+1 from 23-k and 3k+2 from 8+k; indices 24.. are the eliminated clubs.
// perm[i] = league position stored at rank index i.
inline void c41_permutation(const BracketTie* ties, int n, int* perm) {
    for (int k = 0; k < 8; ++k) {
        perm[k] = ties[k].seed;
        perm[23 - k] = ties[k].po_home;
        perm[8 + k] = ties[k].po_away;
    }
    for (int i = 24; i < n; ++i) perm[i] = i;
}

// Old-format Europa League (12 groups of four): the best third of each group.
// `qualified` are the clubs the game already placed in the knockout; the two
// others of a group are 3rd and 4th, separated by points, then their two
// head-to-head matches, then the whole group record.
struct Third { uint32_t id; uint32_t encoded; int points, gd, gf, wins; };

inline int group_thirds(const uint8_t* events, uint32_t capacity, uint16_t competition,
                        const uint32_t* qualified, int nqualified, Third* out) {
    Standing rows[kMaxTeams];
    int unplayed = 0;
    int n = league_table(events, capacity, competition, rows, &unplayed);
    if (n <= 0) return 0;
    int nout = 0;
    for (int g = 1; g < 64; ++g) {
        int cand[kMaxTeams], nc = 0, members = 0;
        for (int i = 0; i < n; ++i) {
            if (rows[i].group != g) continue;
            ++members;
            bool q = false;
            for (int k = 0; k < nqualified; ++k) if (qualified[k] == rows[i].id) q = true;
            if (!q) cand[nc++] = i;
        }
        if (!members) continue;
        if (nc != 2) continue;
        const Standing& a = rows[cand[0]];
        const Standing& b = rows[cand[1]];
        int pick = 0;
        if (a.points != b.points) pick = a.points > b.points ? 0 : 1;
        else {
            int hp[2] = {0, 0}, hgd[2] = {0, 0}, hgf[2] = {0, 0};
            for (uint32_t eid = 0; eid < capacity; ++eid) {
                const uint8_t* ev = events + (uintptr_t)eid * kEventStride;
                if (rd16(ev) != eid) continue;
                uint32_t packed = rd32(ev + 4);
                if ((packed & 0x3FF) != competition || !(packed & kPlayedBit)) continue;
                uint32_t h = team_of(rd32(ev + 0x14)), w = team_of(rd32(ev + 0x18));
                int side;
                if (h == a.id && w == b.id) side = 0;
                else if (h == b.id && w == a.id) side = 1;
                else continue;
                int hg = ev[0x1C], ag = ev[0x1F];
                int x = side, y = 1 - side;       // x is home
                hgf[x] += hg; hgf[y] += ag; hgd[x] += hg - ag; hgd[y] += ag - hg;
                if (hg > ag) hp[x] += 3; else if (ag > hg) hp[y] += 3; else { hp[x]++; hp[y]++; }
            }
            if (hp[0] != hp[1]) pick = hp[0] > hp[1] ? 0 : 1;
            else if (hgd[0] != hgd[1]) pick = hgd[0] > hgd[1] ? 0 : 1;
            else if (hgf[0] != hgf[1]) pick = hgf[0] > hgf[1] ? 0 : 1;
            else pick = ranks_before(a, b) ? 0 : 1;
        }
        const Standing& t = pick ? b : a;
        Third third = {t.id, t.encoded, t.points, t.gf - t.ga, t.gf, t.wins};
        out[nout++] = third;
    }
    for (int i = 1; i < nout; ++i) {
        Third v = out[i];
        int j = i;
        while (j) {
            const Third& p = out[j - 1];
            bool before = v.points != p.points ? v.points > p.points
                        : v.gd != p.gd ? v.gd > p.gd
                        : v.gf != p.gf ? v.gf > p.gf
                        : v.wins != p.wins ? v.wins > p.wins
                        : v.id < p.id;
            if (!before) break;
            out[j] = out[j - 1];
            --j;
        }
        out[j] = v;
    }
    return nout;
}

}  // namespace euro
