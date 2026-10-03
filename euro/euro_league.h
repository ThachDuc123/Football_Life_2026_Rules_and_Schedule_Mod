// euro_league.h -- UEFA 2024+ league phase draw for 36 clubs, pure logic.
//
// Used by ucl32_format (in the game) and test/test_league.cpp (offline).
//   * pots: 4 x 9 by UEFA club coefficient, the title holder first;
//   * opponents: 2 per pot (one at home, one away): 8 matches, 4 at home;
//     never a club of the same association, at most 2 of one association;
//   * since 2026/27 the same fixture with the same home club may not be
//     drawn for a third season in a row (`banned`, from the two previous
//     seasons; the pairing itself stays possible the other way round);
//   * matchdays: 8 rounds of 18 matches, everybody plays every round;
//     one home and one away in every pair of matchdays (1-2, 3-4, 5-6, 7-8),
//     hence also in 1-2 and 7-8 and never three home or three away in a row.
// Deterministic: the same clubs and seed always give the same plan.
#pragma once
#include <stdint.h>

namespace league {

const int kClubs = 36, kPots = 4, kPotSize = 9, kRounds = 8, kMatches = 144;

struct Club {
    uint32_t id;
    uint16_t country;
    int32_t coef;          // UEFA club coefficient x 1000
};

struct Match { uint8_t home, away, round; };

struct Plan {
    int pot[kClubs];       // pot of each club (0..3)
    Match m[kMatches];     // ordered by round
    int attempts;          // draws tried until one fitted
    int relax;             // 0 = every matchday rule, 1 = only "no 3 in a row", 2 = none
};

struct Rng {
    uint32_t s;
    uint32_t next() { uint32_t x = s; x ^= x << 13; x ^= x >> 17; x ^= x << 5; return s = x ? x : 0x9E3779B9u; }
    int below(int n) { return (int)(next() % (uint32_t)n); }
};

template <typename T> inline void shuffle(T* a, int n, Rng& r) {
    for (int i = n - 1; i > 0; --i) { int j = r.below(i + 1); T t = a[i]; a[i] = a[j]; a[j] = t; }
}

// ---------------------------------------------------------------- opponents
struct Draw {
    const Club* clubs;
    int potm[kPots][kPotSize];          // pot -> club index
    bool met[kClubs][kClubs];
    uint8_t per_country[kClubs][kClubs]; // [club][index of the other club's country slot]
    int nedges;
    uint8_t eh[kMatches], ea[kMatches];
    const uint8_t* banned;               // [home * kClubs + away] != 0: not this home fixture
};

inline int country_slot(const Club* clubs, uint16_t c) {
    for (int i = 0; i < kClubs; ++i) if (clubs[i].country == c) return i;
    return 0;
}

inline bool can_meet(const Draw& d, int a, int b) {
    if (a == b || d.met[a][b]) return false;
    const Club& x = d.clubs[a];
    const Club& y = d.clubs[b];
    if (x.country == y.country) return false;
    if (d.per_country[a][country_slot(d.clubs, y.country)] >= 2) return false;
    if (d.per_country[b][country_slot(d.clubs, x.country)] >= 2) return false;
    return true;
}

inline void meet(Draw& d, int home, int away, int delta) {
    d.met[home][away] = d.met[away][home] = delta > 0;
    d.per_country[home][country_slot(d.clubs, d.clubs[away].country)] += delta;
    d.per_country[away][country_slot(d.clubs, d.clubs[home].country)] += delta;
    if (delta > 0) { d.eh[d.nedges] = (uint8_t)home; d.ea[d.nedges] = (uint8_t)away; ++d.nedges; }
    else --d.nedges;
}

// One bijection from pot `from` to pot `to`: hosts[i] (in `from`) plays
// opp[i] (in `to`), `from_hosts` says which side is at home. For a pot with
// itself it is a permutation without fixed points or 2-cycles (a hosts sigma(a)).
inline bool assign(Draw& d, int from, int to, bool from_hosts, Rng& r, int depth, int* opp, bool* used,
                   long* budget) {
    if (depth == kPotSize) return true;
    if (--*budget < 0) return false;
    int a = d.potm[from][depth];
    int order[kPotSize];
    for (int k = 0; k < kPotSize; ++k) order[k] = k;
    shuffle(order, kPotSize, r);
    for (int t = 0; t < kPotSize; ++t) {
        int k = order[t];
        if (used[k]) continue;
        int b = d.potm[to][k];
        if (!can_meet(d, a, b)) continue;
        int home = from_hosts ? a : b, away = from_hosts ? b : a;
        if (d.banned && d.banned[home * kClubs + away]) continue;
        used[k] = true; opp[depth] = k;
        meet(d, home, away, +1);
        if (assign(d, from, to, from_hosts, r, depth + 1, opp, used, budget)) return true;
        meet(d, home, away, -1);
        used[k] = false;
    }
    return false;
}

inline bool draw_opponents(Draw& d, Rng& r) {
    for (int a = 0; a < kClubs; ++a)
        for (int b = 0; b < kClubs; ++b) { d.met[a][b] = false; d.per_country[a][b] = 0; }
    d.nedges = 0;
    // Pot pairs in random order; each needs two bijections (home and away).
    struct Pair { int from, to, side; };
    Pair pairs[20];
    int np = 0;
    for (int p = 0; p < kPots; ++p)
        for (int q = p; q < kPots; ++q)
            for (int side = 0; side < 2; ++side) {
                // A pot with itself: the club hosts one and visits one, so a
                // single bijection covers both sides.
                if (p == q && side == 1) continue;
                Pair x = {p, q, side};
                pairs[np++] = x;
            }
    shuffle(pairs, np, r);
    for (int i = 0; i < np; ++i) {
        int opp[kPotSize]; bool used[kPotSize] = {};
        long budget = 20000;
        if (!assign(d, pairs[i].from, pairs[i].to, pairs[i].side == 0, r, 0, opp, used, &budget)) return false;
    }
    return d.nedges == kMatches;
}

// ------------------------------------------------------------ matchdays
// Matchdays come in four pairs (1-2, 3-4, 5-6, 7-8); in each pair every club
// plays once at home and once away, which gives both UEFA rules for free (one
// home and one away in matchdays 1-2 and 7-8, never three in a row).
// A pair is a cycle cover of the drawn graph (each club hosts one and visits
// one: a perfect matching of the home/away bipartite graph); it splits into
// two matchdays by alternating the edges along each cycle, which needs every
// cycle to have even length.
struct Cover {
    int host_of[kClubs];      // club -> index of the drawn match it hosts
    int seen[kClubs];
};

// Kuhn's augmenting paths on the home->away bipartite graph of the matches
// still unscheduled, in random order. match_in[a] = match where `a` is away.
inline bool kuhn(const Draw& d, const bool* left, int h, int* match_in, bool* visited, const int* perm) {
    for (int t = 0; t < kMatches; ++t) {
        int e = perm[t];
        if (!left[e] || d.eh[e] != h) continue;
        int a = d.ea[e];
        if (visited[a]) continue;
        visited[a] = true;
        if (match_in[a] < 0 || kuhn(d, left, d.eh[match_in[a]], match_in, visited, perm)) {
            match_in[a] = e;
            return true;
        }
    }
    return false;
}

inline bool random_cover(const Draw& d, const bool* left, Rng& r, int* match_in) {
    int perm[kMatches], hosts[kClubs];
    for (int e = 0; e < kMatches; ++e) perm[e] = e;
    shuffle(perm, kMatches, r);
    for (int c = 0; c < kClubs; ++c) { match_in[c] = -1; hosts[c] = c; }
    shuffle(hosts, kClubs, r);
    for (int i = 0; i < kClubs; ++i) {
        bool visited[kClubs] = {};
        if (!kuhn(d, left, hosts[i], match_in, visited, perm)) return false;
    }
    return true;
}

inline bool even_cycles(const Draw& d, const int* match_in) {
    int out[kClubs];                       // club -> club it hosts
    for (int a = 0; a < kClubs; ++a) out[d.eh[match_in[a]]] = a;
    bool seen[kClubs] = {};
    for (int c = 0; c < kClubs; ++c) {
        if (seen[c]) continue;
        int len = 0, v = c;
        while (!seen[v]) { seen[v] = true; v = out[v]; ++len; }
        if (len & 1) return false;
    }
    return true;
}

inline bool split_rounds(const Draw& d, Rng& r, uint8_t* round_of) {
    bool left[kMatches];
    for (int e = 0; e < kMatches; ++e) left[e] = true;
    int covers[4][kClubs];
    for (int k = 0; k < 4; ++k) {
        bool ok = false;
        for (int t = 0; t < 200 && !ok; ++t) {
            if (!random_cover(d, left, r, covers[k])) return false;
            if (!even_cycles(d, covers[k])) continue;
            if (k == 2) {                  // the fourth cover is what remains: check it too
                bool rest[kMatches];
                for (int e = 0; e < kMatches; ++e) rest[e] = left[e];
                for (int a = 0; a < kClubs; ++a) rest[covers[k][a]] = false;
                if (!random_cover(d, rest, r, covers[3]) || !even_cycles(d, covers[3])) continue;
            }
            ok = true;
        }
        if (!ok) return false;
        for (int a = 0; a < kClubs; ++a) left[covers[k][a]] = false;
        if (k == 2) {
            for (int a = 0; a < kClubs; ++a) left[covers[3][a]] = false;
            break;
        }
    }
    int pair_order[4] = {0, 1, 2, 3};
    shuffle(pair_order, 4, r);
    for (int k = 0; k < 4; ++k) {
        int first = 2 * pair_order[k];
        int out_edge[kClubs];
        for (int a = 0; a < kClubs; ++a) out_edge[d.eh[covers[k][a]]] = covers[k][a];
        bool seen[kClubs] = {};
        for (int c = 0; c < kClubs; ++c) {
            if (seen[c]) continue;
            int flip = r.below(2), i = 0, v = c;
            while (!seen[v]) {
                seen[v] = true;
                int e = out_edge[v];
                round_of[e] = (uint8_t)(first + ((i + flip) & 1));
                v = d.ea[e];
                ++i;
            }
        }
    }
    return true;
}

// clubs[36]; holder = id of the title holder (pot 1) or 0; banned as in Draw.
inline bool make_plan(const Club* clubs, uint32_t holder, uint32_t seed, Plan* out,
                      const uint8_t* banned = 0) {
    int order[kClubs];
    for (int i = 0; i < kClubs; ++i) order[i] = i;
    for (int i = 1; i < kClubs; ++i) {             // holder, coefficient, id
        int v = order[i], j = i;
        while (j) {
            const Club& a = clubs[v];
            const Club& b = clubs[order[j - 1]];
            bool before = (a.id == holder) != (b.id == holder) ? a.id == holder
                        : a.coef != b.coef ? a.coef > b.coef : a.id < b.id;
            if (!before) break;
            order[j] = order[j - 1]; --j;
        }
        order[j] = v;
    }
    static Draw d;
    d.clubs = clubs;
    d.banned = banned;
    for (int i = 0; i < kClubs; ++i) {
        d.potm[i / kPotSize][i % kPotSize] = order[i];
        out->pot[order[i]] = i / kPotSize;
    }
    Rng r = {seed ? seed : 0x9E3779B9u};
    uint8_t round_of[kMatches];
    for (int attempt = 1; attempt <= 2000; ++attempt) {
        if (!draw_opponents(d, r)) continue;
        bool split = false;
        for (int s = 0; s < 20 && !split; ++s) split = split_rounds(d, r, round_of);
        if (!split) continue;
        int k = 0;
        for (int round = 0; round < kRounds; ++round)
            for (int e = 0; e < kMatches; ++e)
                if (round_of[e] == round) {
                    out->m[k].home = d.eh[e]; out->m[k].away = d.ea[e]; out->m[k].round = (uint8_t)round;
                    ++k;
                }
        out->attempts = attempt;
        out->relax = 0;
        return k == kMatches;
    }
    return false;
}

// Independent check of every rule; returns the number of violations.
inline int check_plan(const Club* clubs, const Plan& p, int relax, const uint8_t* banned = 0) {
    int bad = 0;
    for (int i = 0; banned && i < kMatches; ++i)
        if (banned[p.m[i].home * kClubs + p.m[i].away]) ++bad;
    int played[kClubs][kRounds] = {};
    int home[kClubs] = {}, potcount[kClubs][kPots][2] = {};
    int pair[kClubs][kClubs] = {};
    for (int i = 0; i < kMatches; ++i) {
        const Match& m = p.m[i];
        played[m.home][m.round]++; played[m.away][m.round]++;
        home[m.home]++;
        potcount[m.home][p.pot[m.away]][0]++;
        potcount[m.away][p.pot[m.home]][1]++;
        pair[m.home][m.away]++; pair[m.away][m.home]++;
        if (clubs[m.home].country == clubs[m.away].country) ++bad;
    }
    for (int c = 0; c < kClubs; ++c) {
        if (home[c] != 4) ++bad;
        for (int r = 0; r < kRounds; ++r) if (played[c][r] != 1) ++bad;
        for (int q = 0; q < kPots; ++q) if (potcount[c][q][0] != 1 || potcount[c][q][1] != 1) ++bad;
        for (int o = 0; o < kClubs; ++o) if (pair[c][o] > 1) ++bad;
        int per[kClubs] = {};
        for (int o = 0; o < kClubs; ++o)
            if (pair[c][o]) for (int x = 0; x < kClubs; ++x) if (clubs[x].country == clubs[o].country) { per[x]++; break; }
        for (int x = 0; x < kClubs; ++x) if (per[x] > 2) ++bad;
        int8_t ha[kRounds] = {};
        for (int i = 0; i < kMatches; ++i) {
            if (p.m[i].home == c) ha[p.m[i].round] = 1;
            if (p.m[i].away == c) ha[p.m[i].round] = -1;
        }
        if (relax < 1 && (ha[0] == ha[1] || ha[6] == ha[7])) ++bad;
        if (relax < 2) for (int r = 2; r < kRounds; ++r) if (ha[r] == ha[r - 1] && ha[r] == ha[r - 2]) ++bad;
    }
    return bad;
}

}  // namespace league
