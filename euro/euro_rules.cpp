// euro_rules.cpp -- UEFA 2024+ knockout rules on top of ucl32_c41.dll (C.4.1).
//
// ucl32_c41 already turns the UCL knockout into the native 24-club bracket
// (8 byes + 8 play-offs) and moves dates/progression; it is kept as is. This
// DLL changes three things around it, all in memory, nothing on disk:
//
//   1. c41's sort_table is replaced: the league phase is ranked with every
//      criterion of Article 18.01, and the rank index c41 reads is permuted so
//      its fixed vector (slot 3k = index k, 3k+1 = 23-k, 3k+2 = 8+k) becomes the
//      real bracket (euro_core.h build_bracket).
//   2. The competition-advance call is wrapped: after c41 has handled the end
//      of the Europa League groups (comp 5), every UCL club in the UEL knockout
//      (native group thirds, or c41's UCL 25th-32nd) is replaced by the best
//      Europa League group thirds. Since 2024 nobody drops from the UCL.
//   3. c41's knockout date table gets the real UEFA calendar: play-offs Feb
//      16/23, round of 16 Mar 9/16, quarter-finals Apr 6/13, semi-finals Apr
//      27/May 4. The final stays on day 149 (the game's season ends in May).
//
// Hard guards: base address, c41 code bytes, the native writer prologue and
// the c41 date rows are verified before anything is written; any mismatch
// leaves c41's own behaviour untouched and is logged in euro_rules.log.

#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include "euro_core.h"

using namespace euro;

static const uintptr_t kImageBase = 0x140000000ULL;
static const uintptr_t kGlobalRootPtr = kImageBase + 0x03705E10;
static const uintptr_t kModelOffset = 0x48;
static const uintptr_t kComps = 0x00C12E9C;
static const uint32_t kCompStride = 0x314;
static const uintptr_t kCompCount = 0x00D0BCF4;
static const uintptr_t kEvents = 0x00E9FF08;
static const uintptr_t kCalendar = 0x016038A8;
static const uintptr_t kCalendarYear = 0x3F176;

static const uintptr_t kAdvanceCall = kImageBase + 0x01348340;   // call rel32 in sub_01348210
static const uintptr_t kAdvanceNative = kImageBase + 0x01345CC0;
static const uintptr_t kWriteParts = kImageBase + 0x01522B50;    // (comp, vector<u32>*, 1)
static const unsigned char kWritePartsSig[24] = {
    0x48,0x89,0x5C,0x24,0x08,0x48,0x89,0x6C,0x24,0x10,0x48,0x89,
    0x74,0x24,0x18,0x57,0x48,0x83,0xEC,0x20,0x41,0x0F,0xB6,0xE8
};
static const uintptr_t kDatesJump = kImageBase + 0x0158147A;     // c41 C3: jmp to trampoline

// ucl32_c41.dll C.4.1 (sha in UCL32-Mod/install.json), relative to its base.
static const uint32_t kC41Sort = 0x1340;
static const uint32_t kC41NTeams = 0x1316C;
static const uint32_t kC41RankIdx = 0x13060;
static const uint32_t kC41Teams = 0x13180;
static const unsigned char kC41SortSig[64] = {
    0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x55,0x57,0x56,0x53,0x48,0x83,0xEC,0x28,
    0x8B,0x0D,0x16,0x1E,0x01,0x00,0x85,0xC9,0x0F,0x84,0x3C,0x01,0x00,0x00,0x41,0x89,
    0xC8,0x31,0xC0,0x4C,0x8D,0x3D,0xF6,0x1C,0x01,0x00,0xF6,0xC1,0x01,0x74,0x31,0xC7,
    0x05,0xE7,0x1C,0x01,0x00,0x00,0x00,0x00,0x00,0xB8,0x01,0x00,0x00,0x00,0x4C,0x39
};

struct DateRow { uint32_t day, code, leg; };
static const DateRow kC41Dates[9] = {
    {54,46,0},{75,46,1},{82,47,0},{89,47,1},{96,51,0},{103,51,1},{117,52,0},{124,52,1},{149,53,2}
};
// 2026/27: 16/23 Feb, 9/16 Mar, 6/13 Apr, 27 Apr/4 May (day 0 = 1 January).
static const uint32_t kRealDays[9] = {46, 53, 67, 74, 95, 102, 116, 123, 149};

static const char kLogName[] = "euro_rules.log";
static CRITICAL_SECTION g_log_lock;
static bool g_log_ready = false;

static void log_line(const char* text) {
    if (!g_log_ready) return;
    SYSTEMTIME st;
    GetLocalTime(&st);
    char line[1024];
    int n = wsprintfA(line, "%02u:%02u:%02u | ", (unsigned)st.wHour, (unsigned)st.wMinute, (unsigned)st.wSecond);
    int len = lstrlenA(text);
    if (len > (int)sizeof(line) - n - 3) len = (int)sizeof(line) - n - 3;
    CopyMemory(line + n, text, len);
    n += len;
    line[n++] = '\r'; line[n++] = '\n';
    EnterCriticalSection(&g_log_lock);
    HANDLE h = CreateFileA(kLogName, FILE_APPEND_DATA, FILE_SHARE_READ, NULL,
        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h != INVALID_HANDLE_VALUE) {
        DWORD written = 0;
        WriteFile(h, line, (DWORD)n, &written, NULL);
        CloseHandle(h);
    }
    LeaveCriticalSection(&g_log_lock);
}

static bool readable(const void* p, size_t span) {
    if (!p) return false;
    MEMORY_BASIC_INFORMATION mbi;
    if (!VirtualQuery(p, &mbi, sizeof(mbi))) return false;
    if (mbi.State != MEM_COMMIT || (mbi.Protect & PAGE_GUARD)) return false;
    DWORD ok = PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY |
        PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY;
    uintptr_t a = (uintptr_t)p;
    uintptr_t end = (uintptr_t)mbi.BaseAddress + mbi.RegionSize;
    return (mbi.Protect & ok) && a >= (uintptr_t)mbi.BaseAddress && a + span <= end;
}

// The Event table spans several megabytes: walk every region it crosses.
static bool readable_span(const void* p, size_t span) {
    uintptr_t a = (uintptr_t)p, end = a + span;
    while (a < end) {
        MEMORY_BASIC_INFORMATION mbi;
        if (!VirtualQuery((const void*)a, &mbi, sizeof(mbi))) return false;
        if (mbi.State != MEM_COMMIT || (mbi.Protect & PAGE_GUARD)) return false;
        DWORD ok = PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY |
            PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY;
        if (!(mbi.Protect & ok)) return false;
        a = (uintptr_t)mbi.BaseAddress + mbi.RegionSize;
    }
    return true;
}

static bool same_bytes(uintptr_t addr, const unsigned char* want, uint32_t n) {
    if (!readable((const void*)addr, n)) return false;
    for (uint32_t i = 0; i < n; ++i) if (((const unsigned char*)addr)[i] != want[i]) return false;
    return true;
}

static bool write_code(uintptr_t addr, const void* bytes, uint32_t n) {
    DWORD old = 0, ignored = 0;
    if (!VirtualProtect((void*)addr, n, PAGE_EXECUTE_READWRITE, &old)) return false;
    CopyMemory((void*)addr, bytes, n);
    FlushInstructionCache(GetCurrentProcess(), (const void*)addr, n);
    VirtualProtect((void*)addr, n, old, &ignored);
    return same_bytes(addr, (const unsigned char*)bytes, n);
}

// JMP [RIP+0] followed by the absolute target: no register is touched.
static void absolute_jump(unsigned char* out, uintptr_t target) {
    out[0] = 0xFF; out[1] = 0x25;
    out[2] = out[3] = out[4] = out[5] = 0;
    for (int i = 0; i < 8; ++i) out[6 + i] = (unsigned char)(target >> (i * 8));
}

static uintptr_t model_base() {
    if (!readable((const void*)kGlobalRootPtr, sizeof(uintptr_t))) return 0;
    uintptr_t root = *(const uintptr_t*)kGlobalRootPtr;
    if (!readable((const void*)(root + kModelOffset), sizeof(uintptr_t))) return 0;
    uintptr_t model = *(const uintptr_t*)(root + kModelOffset);
    if (!readable_span((const void*)(model + kEvents), (size_t)kEventStride * kEventCapacity)) return 0;
    return model;
}

static uint16_t season_year(uintptr_t model) {
    uintptr_t at = model + kCalendar + kCalendarYear;
    return readable((const void*)at, 2) ? *(const uint16_t*)at : 0;
}

static uintptr_t find_comp(uintptr_t model, uint16_t id) {
    if (!readable((const void*)(model + kCompCount), 4)) return 0;
    uint32_t count = *(const uint32_t*)(model + kCompCount);
    if (count > 300) count = 300;
    for (uint32_t i = 0; i < count; ++i) {
        uintptr_t rec = model + kComps + (uintptr_t)i * kCompStride;
        if (!readable((const void*)rec, kCompStride)) return 0;
        if (*(const uint16_t*)rec == id) return rec;
    }
    return 0;
}

static uint32_t comp_participants(uintptr_t rec, uint32_t* out, uint32_t cap) {
    uint32_t n = (*(const uint32_t*)(rec + 0x308) >> 16) & 0x7F;
    if (n > cap) n = cap;
    for (uint32_t i = 0; i < n; ++i) out[i] = *(const uint32_t*)(rec + 0x170 + i * 4);
    return n;
}

// ------------------------------------------------------------ 1. league ranking
struct C41Team { uint32_t encoded, id, played, wins, draws, losses, points, gf, ga; };
static uint8_t* g_c41 = NULL;
static uint32_t g_logged_seed = 0;

// c41's own order (points, goal difference, goals, wins, encoded): the fallback
// whenever the event table cannot be trusted.
static void c41_plain_order(uint32_t n, const C41Team* t, uint32_t* idx) {
    for (uint32_t i = 0; i < n; ++i) idx[i] = i;
    for (uint32_t i = 1; i < n; ++i) {
        uint32_t v = idx[i], j = i;
        while (j) {
            const C41Team& a = t[v];
            const C41Team& b = t[idx[j - 1]];
            int gda = (int)a.gf - (int)a.ga, gdb = (int)b.gf - (int)b.ga;
            bool before = a.points != b.points ? a.points > b.points
                        : gda != gdb ? gda > gdb
                        : a.gf != b.gf ? a.gf > b.gf
                        : a.wins != b.wins ? a.wins > b.wins
                        : a.encoded < b.encoded;
            if (!before) break;
            idx[j] = idx[j - 1];
            --j;
        }
        idx[j] = v;
    }
}

// The game's world club ranking (model+0x16705A8, 16-byte rows {team, place,
// points, tier}, updated every season) stands for the club coefficient: last
// league tie-breaker here, pots and the extra UCL places in the hooks below.
static void fill_ranks(uintptr_t model, Standing* rows, int n) {
    uintptr_t at = model + 0x016705A8;
    if (!readable((const void*)at, 16 * 1024)) return;
    for (uint32_t i = 0; i < 1024; ++i) {
        uint32_t enc = *(const uint32_t*)(at + i * 16);
        if (enc == 0xFFFFFFFF) break;
        uint32_t place = *(const uint32_t*)(at + i * 16 + 4);
        for (int k = 0; k < n; ++k)
            if (rows[k].id == team_of(enc)) rows[k].rank = place >= 1 && place <= 4096 ? place : kUnranked;
    }
}

static void log_table(uint16_t year, const Standing* rows, const int* order, int n,
                      const BracketTie* ties) {
    char msg[320];
    wsprintfA(msg, "LEAGUE %u: %d clubs, Article 18.01 order", (unsigned)year, n);
    log_line(msg);
    for (int p = 0; p < n; ++p) {
        const Standing& s = rows[order[p]];
        wsprintfA(msg, "RANK %02d t%u pts=%d gd=%d gf=%d away_gf=%d w=%d away_w=%d opp_pts=%d opp_gd=%d opp_gf=%d disc=%d club_rank=%u %s",
            p + 1, s.id, s.points, s.gf - s.ga, s.gf, s.away_gf, s.wins, s.away_wins,
            s.opp_points, s.opp_gd, s.opp_gf, s.discipline, s.rank,
            p < 8 ? "[r16]" : p < 24 ? "[playoff]" : "[out]");
        log_line(msg);
    }
    static const char* const kSection = "ADBCADBC";
    for (int k = 0; k < 8; ++k) {
        wsprintfA(msg, "BRACKET %s R16-%d (%c): %d v winner(%d at home first, %d hosts 2nd leg) -> QF%d",
            k < 4 ? "upper" : "lower", k + 1, kSection[k], ties[k].seed + 1,
            ties[k].po_home + 1, ties[k].po_away + 1, k / 2 + 1);
        log_line(msg);
    }
}

static void euro_sort(void) {
    uint32_t n = *(volatile uint32_t*)(g_c41 + kC41NTeams);
    C41Team* teams = (C41Team*)(g_c41 + kC41Teams);
    uint32_t* idx = (uint32_t*)(g_c41 + kC41RankIdx);
    if (n > 32) n = 32;
    c41_plain_order(n, teams, idx);
    if (n != 32) { log_line("SORT fallback: c41 table does not have 32 clubs"); return; }
    uintptr_t model = model_base();
    if (!model) { log_line("SORT fallback: model not readable"); return; }
    static Standing rows[kMaxTeams];
    int unplayed = 0;
    int m = league_table((const uint8_t*)(model + kEvents), kEventCapacity, 3, rows, &unplayed);
    if (m > 0) fill_ranks(model, rows, m);
    if (m != 32) {
        char msg[128];
        wsprintfA(msg, "SORT fallback: league phase has %d clubs", m);
        log_line(msg);
        return;
    }
    int order[kMaxTeams];
    rank_order(rows, m, order);
    uint32_t to_c41[32], ranked_ids[32];
    for (int p = 0; p < 32; ++p) {
        ranked_ids[p] = rows[order[p]].id;
        uint32_t i = 0;
        while (i < n && teams[i].id != ranked_ids[p]) ++i;
        if (i == n) { log_line("SORT fallback: a league club is missing from c41's table"); return; }
        to_c41[p] = i;
    }
    uint16_t year = season_year(model);
    uint32_t seed = draw_seed(year, ranked_ids, 24);
    BracketTie ties[8];
    build_bracket(seed, ties);
    int perm[32];
    c41_permutation(ties, 32, perm);
    for (int i = 0; i < 32; ++i) idx[i] = to_c41[perm[i]];
    if (seed != g_logged_seed) {
        g_logged_seed = seed;
        if (unplayed) {
            char msg[128];
            wsprintfA(msg, "SORT note: %d league matches still unplayed", unplayed);
            log_line(msg);
        }
        log_table(year, rows, order, m, ties);
    }
}

// ------------------------------------------------- 2. Europa League knockout
typedef uint64_t (*advance_fn)(void*, uint32_t, void*);
typedef void (*write_parts_fn)(uint64_t, void*, uint64_t);
static advance_fn g_c41_advance = NULL;
struct U32Vector { uint32_t* begin; uint32_t* end; uint32_t* cap; };

static void uel_without_ucl_clubs() {
    uintptr_t model = model_base();
    if (!model) return;
    uintptr_t uel = find_comp(model, 6), ucl = find_comp(model, 3);
    if (!uel || !ucl) { log_line("UEL skipped: competition 3 or 6 not found"); return; }
    uint32_t parts[48], ucl_parts[48];
    uint32_t n = comp_participants(uel, parts, 48);
    uint32_t nu = comp_participants(ucl, ucl_parts, 48);
    if (n != 32 || nu == 0) {
        char msg[128];
        wsprintfA(msg, "UEL skipped: knockout has %u clubs, UCL league %u", n, nu);
        log_line(msg);
        return;
    }
    uint32_t pos[48], qualified[48], npos = 0, nq = 0;
    for (uint32_t i = 0; i < n; ++i) {
        bool from_ucl = false;
        for (uint32_t k = 0; k < nu; ++k) if (team_of(ucl_parts[k]) == team_of(parts[i])) from_ucl = true;
        if (from_ucl) pos[npos++] = i;
        else qualified[nq++] = team_of(parts[i]);
    }
    if (!npos) { log_line("UEL ok: no UCL club in the Europa League knockout"); return; }
    static Standing groups[kMaxTeams];
    int unplayed = 0;
    if (league_table((const uint8_t*)(model + kEvents), kEventCapacity, 5, groups, &unplayed) <= 0 || unplayed) {
        char msg[128];
        wsprintfA(msg, "UEL skipped: %d Europa League group matches unplayed", unplayed);
        log_line(msg);
        return;
    }
    Third thirds[64];
    int nt = group_thirds((const uint8_t*)(model + kEvents), kEventCapacity, 5, qualified, (int)nq, thirds);
    if (nt < (int)npos) {
        char msg[160];
        wsprintfA(msg, "UEL blocked: %u UCL clubs to replace but only %d group thirds", npos, nt);
        log_line(msg);
        return;
    }
    if (!same_bytes(kWriteParts, kWritePartsSig, sizeof(kWritePartsSig))) {
        log_line("UEL blocked: native participant writer differs");
        return;
    }
    uint32_t wanted[48];
    for (uint32_t i = 0; i < n; ++i) wanted[i] = parts[i];
    char msg[256];
    for (uint32_t k = 0; k < npos; ++k) {
        wsprintfA(msg, "UEL slot %u: UCL club t%u -> group third t%u (pts=%d gd=%d gf=%d)",
            pos[k], team_of(parts[pos[k]]), thirds[k].id, thirds[k].points, thirds[k].gd, thirds[k].gf);
        log_line(msg);
        wanted[pos[k]] = thirds[k].encoded;
    }
    U32Vector vec = {wanted, wanted + n, wanted + n};
    ((write_parts_fn)kWriteParts)(6, &vec, 1);
    uint32_t after[48];
    uint32_t na = comp_participants(uel, after, 48);
    bool same = na == n;
    for (uint32_t i = 0; same && i < n; ++i) if (team_of(after[i]) != team_of(wanted[i])) same = false;
    wsprintfA(msg, same ? "UEL VERIFIED: %u UCL clubs replaced by Europa League thirds"
                        : "UEL ERROR: reread differs after replacing %u clubs", npos);
    log_line(msg);
}

// 36-club league phase (4 groups of 9 in the regulation): when it ends, the
// knockout gets the 24 best of the single table in the 2025/26 bracket order
// (slot 3k waits in the round of 16, 3k+1 hosts the play-off first leg, 3k+2
// the second leg); 25th-36th are out. c41 sees a non-32 phase and writes nothing.
static bool league36_comp(uintptr_t model, uint16_t comp) {
    uintptr_t rec = find_comp(model, comp);
    return rec && (*(const uint8_t*)(rec + 0x307) & 0x3F) == 4;
}

static void knockout_from_league36(uint16_t league_comp, uint16_t ko_comp) {
    uintptr_t model = model_base();
    if (!model || !league36_comp(model, league_comp)) return;
    char msg[192];
    static Standing rows[kMaxTeams];
    int unplayed = 0;
    int n = league_table((const uint8_t*)(model + kEvents), kEventCapacity, league_comp, rows, &unplayed);
    if (n > 0) fill_ranks(model, rows, n);
    if (n != 36 || unplayed) {
        wsprintfA(msg, "KO36 comp %u blocked: league phase %d clubs, %d unplayed", league_comp, n, unplayed);
        log_line(msg);
        return;
    }
    uintptr_t ko = find_comp(model, ko_comp);
    if (!ko || !same_bytes(kWriteParts, kWritePartsSig, sizeof(kWritePartsSig))) {
        log_line("KO36 blocked: knockout competition or native writer not found");
        return;
    }
    int order[kMaxTeams];
    rank_order(rows, n, order);
    uint32_t ids[kMaxTeams];
    for (int p = 0; p < n; ++p) ids[p] = rows[order[p]].id;
    uint16_t year = season_year(model);
    BracketTie ties[8];
    build_bracket(draw_seed(year, ids, 24), ties);
    uint32_t vec24[24];
    for (int k = 0; k < 8; ++k) {
        vec24[3 * k] = rows[order[ties[k].seed]].encoded;
        vec24[3 * k + 1] = rows[order[ties[k].po_home]].encoded;
        vec24[3 * k + 2] = rows[order[ties[k].po_away]].encoded;
    }
    log_table(year, rows, order, n, ties);
    U32Vector vec = {vec24, vec24 + 24, vec24 + 24};
    ((write_parts_fn)kWriteParts)(ko_comp, &vec, 1);
    uint32_t after[48];
    uint32_t na = comp_participants(ko, after, 48);
    bool same = na == 24;
    for (uint32_t i = 0; same && i < 24; ++i) if (team_of(after[i]) != team_of(vec24[i])) same = false;
    wsprintfA(msg, same ? "KO36 VERIFIED comp %u: 24 clubs from the comp %u single table, 25th-36th out"
                        : "KO36 ERROR comp %u: reread differs (comp %u)", ko_comp, league_comp);
    log_line(msg);
}

// Called for every competition that played today; like c41, act only when the
// game reports the stage finished (al != 0).
static uint64_t euro_advance(void* ctx, uint32_t comp, void* out) {
    uint64_t result = g_c41_advance(ctx, comp, out);
    uint16_t id = (uint16_t)comp;
    if ((id == 3 || id == 5) && (result & 0xFF)) {
        uintptr_t model = model_base();
        if (model && league36_comp(model, id)) knockout_from_league36(id, id == 3 ? 4 : 6);
        else if (id == 5) uel_without_ucl_clubs();
    }
    return result;
}

static uintptr_t alloc_near(uintptr_t site) {
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    uintptr_t gran = si.dwAllocationGranularity ? si.dwAllocationGranularity : 0x10000;
    for (uintptr_t delta = 0x01000000; delta < 0x7F000000; delta += gran) {
        for (int dir = 0; dir < 2; ++dir) {
            uintptr_t at = dir ? site + delta : site - delta;
            at &= ~(gran - 1);
            MEMORY_BASIC_INFORMATION mbi;
            if (!VirtualQuery((void*)at, &mbi, sizeof(mbi)) || mbi.State != MEM_FREE) continue;
            void* p = VirtualAlloc((void*)at, 0x1000, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
            if (p) return (uintptr_t)p;
        }
    }
    return 0;
}

static bool hook_advance() {
    if (!same_bytes(kAdvanceCall, (const unsigned char*)"\xE8", 1)) {
        log_line("ABORT advance: call site is not a call");
        return false;
    }
    int32_t rel = *(const int32_t*)(kAdvanceCall + 1);
    uintptr_t target = kAdvanceCall + 5 + (intptr_t)rel;
    if (target == kAdvanceNative) {
        log_line("ABORT advance: ucl32_c41 hook is not active");
        return false;
    }
    if (!readable((const void*)target, 14)) {
        log_line("ABORT advance: current call target not readable");
        return false;
    }
    uintptr_t cave = alloc_near(kAdvanceCall);
    if (!cave) { log_line("ABORT advance: no cave within rel32"); return false; }
    absolute_jump((unsigned char*)cave, (uintptr_t)&euro_advance);
    FlushInstructionCache(GetCurrentProcess(), (const void*)cave, 14);
    intptr_t nrel = (intptr_t)cave - (intptr_t)(kAdvanceCall + 5);
    if (nrel > 0x7FFFFFFF || nrel < -(intptr_t)0x80000000LL) {
        VirtualFree((void*)cave, 0, MEM_RELEASE);
        log_line("ABORT advance: cave out of rel32");
        return false;
    }
    g_c41_advance = (advance_fn)target;
    unsigned char call[5] = {0xE8};
    int32_t r32 = (int32_t)nrel;
    CopyMemory(call + 1, &r32, 4);
    if (!write_code(kAdvanceCall, call, 5)) {
        log_line("ABORT advance: readback of the call differs");
        return false;
    }
    char msg[160];
    wsprintfA(msg, "PATCHED advance call -> cave 0x%08X%08X -> c41 0x%08X%08X",
        (unsigned)(cave >> 32), (unsigned)cave, (unsigned)(target >> 32), (unsigned)target);
    log_line(msg);
    return true;
}

// ------------------------------------------------------------- 3. dates
static void real_dates() {
    if (!same_bytes(kDatesJump, (const unsigned char*)"\xE9", 1)) {
        log_line("DATES skipped: c41 C3 date patch is not active");
        return;
    }
    uintptr_t tramp = kDatesJump + 5 + (intptr_t)*(const int32_t*)(kDatesJump + 1);
    DateRow* rows = (DateRow*)(tramp + 0x40);
    if (!readable(rows, sizeof(kC41Dates))) { log_line("DATES skipped: c41 table not readable"); return; }
    bool c41 = true, done = true;
    for (int i = 0; i < 9; ++i) {
        if (rows[i].code != kC41Dates[i].code || rows[i].leg != kC41Dates[i].leg) { c41 = done = false; break; }
        if (rows[i].day != kC41Dates[i].day) c41 = false;
        if (rows[i].day != kRealDays[i]) done = false;
    }
    if (done) { log_line("DATES already real"); return; }
    if (!c41) { log_line("DATES skipped: c41 table differs from C.4.1"); return; }
    DateRow wanted[9];
    for (int i = 0; i < 9; ++i) { wanted[i] = rows[i]; wanted[i].day = kRealDays[i]; }
    if (!write_code((uintptr_t)rows, wanted, sizeof(wanted))) { log_line("DATES ERROR: readback differs"); return; }
    log_line("DATES real calendar: play-off 46/53, R16 67/74, QF 95/102, SF 116/123, final 149");
}

// ------------------------------------------- 4. 36-club league phase (step 1)
// Active only when CompetitionRegulation gives the UCL/UEL league phase four
// groups (livecpk/UEFA36): 4 groups of 9 clubs, single round robin = 8 matches
// per club, 144 matches. Seasons created with the old regulation keep 8 groups
// and these hooks do nothing.
//   * entrants: when the UCL play-off ends the game seeds the UCL league phase
//     (comp 3) with 32 clubs; the 4 play-off losers best placed in the game's
//     world club ranking (the ranking that also makes the pots) are added (36).
//     The Europa League (comp 5) then gets 40 direct entrants + 8 play-off
//     losers; the 4 losers now in the UCL and the last direct entrants are
//     dropped to keep 36.
//   * dates (UEFA calendar, matchdays 3-8 as in 2026/27): UCL Tuesday
//     15/9, 29/9, 20/10, 3/11, 24/11, 8/12, 19/1, Wednesday 27/1; UEL Thursday
//     24/9, 1/10, 22/10, 5/11, 26/11, 10/12, 21/1, 28/1. The ninth row is only
//     there for the ninth native round, which the fixture generator empties.
static const uintptr_t kSeedFn = kImageBase + 0x0155A600;    // (comp, vector<u32>*, flag)
static const unsigned char kSeedSig[18] = {
    0x40,0x56,0x57,0x41,0x56,0x48,0x83,0xEC,0x30,0x48,0xC7,0x44,0x24,0x20,0xFE,0xFF,0xFF,0xFF
};
static const uintptr_t kRowsFn = kImageBase + 0x01581410;    // (comp, vector<DateRow>*, bool*)
static const unsigned char kRowsSig[15] = {
    0x48,0x89,0x5C,0x24,0x10,0x48,0x89,0x74,0x24,0x18,0x57,0x48,0x83,0xEC,0x20
};
static const uintptr_t kAppendFn = kImageBase + 0x01529620;  // vector<u32> += vector<u32>
static const uintptr_t kPushRowFn = kImageBase + 0x01586640; // vector<DateRow>::push_back
static const uint32_t kLeagueDays[9] = {257, 271, 292, 306, 327, 341, 18, 26, 33};
static const uint32_t kUelDays[9] = {266, 273, 294, 308, 329, 343, 20, 27, 34};

typedef uint64_t (*seed_fn)(uint64_t, void*, uint64_t);
typedef void (*rows_fn)(uint64_t, void*, uint8_t*);
typedef void (*append_fn)(void*, void*);
typedef void (*push_row_fn)(void*, const DateRow*);
static seed_fn g_seed_orig = NULL;
static rows_fn g_rows_orig = NULL;

static bool league36(uintptr_t model, uint16_t comp) {
    uintptr_t rec = find_comp(model, comp);
    return rec && (*(const uint8_t*)(rec + 0x307) & 0x3F) == 4;
}

static bool in_list(const uint32_t* list, uint32_t n, uint32_t team) {
    for (uint32_t i = 0; i < n; ++i) if (team_of(list[i]) == team) return true;
    return false;
}

struct Loser { uint32_t encoded; uint32_t rank; int diff, gf; };

// Place in the game's world club ranking (model+0x16705A8, 16-byte rows
// {team, rank, points, tier}, updated every season); 0 when not ranked.
static uint32_t club_rank(uintptr_t model, uint32_t team) {
    uintptr_t at = model + 0x016705A8;
    if (!readable((const void*)at, 16 * 1024)) return 0;
    for (uint32_t i = 0; i < 1024; ++i) {
        uint32_t enc = *(const uint32_t*)(at + i * 16);
        if (enc == 0xFFFFFFFF) break;
        uint32_t rank = *(const uint32_t*)(at + i * 16 + 4);
        if (team_of(enc) == team) return rank >= 1 && rank <= 4096 ? rank : 0;
    }
    return 0;
}

// UCL play-off losers (comp 2, two-legged ties) ordered by the world club
// ranking, then the narrowest aggregate defeat, then goals scored, then team id.
static uint32_t playoff_losers(uintptr_t model, const uint32_t* entrants, uint32_t nentrants,
                               Loser* out, uint32_t cap) {
    uintptr_t po = find_comp(model, 2);
    if (!po) return 0;
    uint32_t parts[48];
    uint32_t np = comp_participants(po, parts, 48), n = 0;
    const uint8_t* events = (const uint8_t*)(model + kEvents);
    for (uint32_t i = 0; i < np && n < cap; ++i) {
        uint32_t t = team_of(parts[i]);
        if (in_list(entrants, nentrants, t)) continue;          // a winner
        int gf = 0, ga = 0, legs = 0;
        for (uint32_t eid = 0; eid < kEventCapacity; ++eid) {
            const uint8_t* ev = events + (uintptr_t)eid * kEventStride;
            if (rd16(ev) != eid || (rd32(ev + 4) & 0x3FF) != 2 || !(rd32(ev + 4) & kPlayedBit)) continue;
            uint32_t h = team_of(rd32(ev + 0x14)), a = team_of(rd32(ev + 0x18));
            if (h != t && a != t) continue;
            int hg = ev[0x1C] + ev[0x1D], ag = ev[0x1F] + ev[0x20];
            gf += h == t ? hg : ag;
            ga += h == t ? ag : hg;
            ++legs;
        }
        if (!legs) continue;
        uint32_t rank = club_rank(model, t);
        Loser l = {parts[i], rank ? rank : 100000u, gf - ga, gf};
        uint32_t j = n++;
        while (j) {
            const Loser& p = out[j - 1];
            bool after = p.rank != l.rank ? p.rank > l.rank
                       : p.diff != l.diff ? p.diff < l.diff
                       : p.gf != l.gf ? p.gf < l.gf
                       : team_of(p.encoded) > team_of(l.encoded);
            if (!after) break;
            out[j] = out[j - 1];
            --j;
        }
        out[j] = l;
    }
    return n;
}

static void adjust_entrants(uint16_t comp, U32Vector* vec) {
    uintptr_t model = model_base();
    if (!model || !vec || !vec->begin || !league36(model, comp)) return;
    uint32_t n = (uint32_t)(vec->end - vec->begin);
    char msg[256];
    if (comp == 3) {
        if (n != 32) {
            wsprintfA(msg, "ENTRANTS UCL: %u clubs before the draw (expected 32), unchanged", n);
            log_line(msg);
            return;
        }
        Loser losers[16];
        uint32_t nl = playoff_losers(model, vec->begin, n, losers, 16);
        if (nl < 4) {
            wsprintfA(msg, "ENTRANTS UCL blocked: only %u play-off losers found", nl);
            log_line(msg);
            return;
        }
        uint32_t extra[4];
        for (int i = 0; i < 4; ++i) {
            extra[i] = losers[i].encoded;
            wsprintfA(msg, "ENTRANTS UCL +t%u (play-off loser, club ranking #%u, aggregate %d)",
                team_of(extra[i]), losers[i].rank, losers[i].diff);
            log_line(msg);
        }
        U32Vector add = {extra, extra + 4, extra + 4};
        ((append_fn)kAppendFn)(vec, &add);
        wsprintfA(msg, "ENTRANTS UCL: %u clubs", (unsigned)(vec->end - vec->begin));
        log_line(msg);
    } else if (comp == 5) {
        uintptr_t ucl = find_comp(model, 3), po = find_comp(model, 2);
        if (!ucl || !po) return;
        uint32_t ucl_parts[48], po_parts[48];
        uint32_t nu = comp_participants(ucl, ucl_parts, 48);
        uint32_t np = comp_participants(po, po_parts, 48);
        uint32_t keep[64], nk = 0, losers_kept = 0, direct = 0;
        for (uint32_t i = 0; i < n; ++i) {
            uint32_t t = team_of(vec->begin[i]);
            if (!in_list(po_parts, np, t)) ++direct;
            else if (!in_list(ucl_parts, nu, t)) ++losers_kept;
        }
        if (n < 36 || direct < 36 - losers_kept) {
            wsprintfA(msg, "ENTRANTS UEL: %u clubs (%u direct, %u play-off losers), unchanged", n, direct, losers_kept);
            log_line(msg);
            return;
        }
        uint32_t direct_keep = 36 - losers_kept, seen_direct = 0;
        for (uint32_t i = 0; i < n && nk < 64; ++i) {
            uint32_t enc = vec->begin[i], t = team_of(enc);
            bool loser = in_list(po_parts, np, t);
            if (loser && in_list(ucl_parts, nu, t)) {
                wsprintfA(msg, "ENTRANTS UEL -t%u (moved to the UCL)", t);
                log_line(msg);
                continue;
            }
            if (!loser && seen_direct++ >= direct_keep) {
                wsprintfA(msg, "ENTRANTS UEL -t%u (direct entrant beyond 36)", t);
                log_line(msg);
                continue;
            }
            keep[nk++] = enc;
        }
        if (nk != 36) {
            wsprintfA(msg, "ENTRANTS UEL blocked: %u clubs after trimming", nk);
            log_line(msg);
            return;
        }
        for (uint32_t i = 0; i < nk; ++i) vec->begin[i] = keep[i];
        vec->end = vec->begin + nk;
        log_line("ENTRANTS UEL: 36 clubs");
    }
}

static uint64_t euro_seed(uint64_t comp, void* vec, uint64_t flag) {
    uint16_t id = (uint16_t)comp;
    if (id == 3 || id == 5) adjust_entrants(id, (U32Vector*)vec);
    return g_seed_orig(comp, vec, flag);
}

// Europa League knockout (comp 6): the native rows are already the UEFA
// 2026/27 dates (play-offs 18/25 Feb, round of 16 11/18 Mar, quarter-finals
// 8/15 Apr, semi-finals 29 Apr/6 May); only the final moves from 20 to 26 May.
static const uintptr_t kUelKnockoutRows = kImageBase + 0x0298DF60;
static const DateRow kUelKnockoutNative[9] = {
    {48,46,0},{55,46,1},{69,47,0},{76,47,1},{97,51,0},{104,51,1},{118,52,0},{125,52,1},{139,53,2}
};
static const uint32_t kUelFinalDay = 145;

static void euro_rows(uint64_t comp, void* rows, uint8_t* flag) {
    uint16_t id = (uint16_t)comp, base = id & 0x3FF, group = id >> 10;
    if (id == 6 && same_bytes(kUelKnockoutRows, (const unsigned char*)kUelKnockoutNative, sizeof(kUelKnockoutNative))) {
        *flag = 0;
        for (int r = 0; r < 9; ++r) {
            DateRow row = kUelKnockoutNative[r];
            if (row.code == 53) row.day = kUelFinalDay;
            ((push_row_fn)kPushRowFn)(rows, &row);
        }
        return;
    }
    if ((base == 3 || base == 5) && group >= 1 && group <= 4) {
        uintptr_t model = model_base();
        if (model && league36(model, base)) {
            *flag = 0;
            for (uint32_t r = 0; r < 9; ++r) {
                DateRow row = {base == 5 ? kUelDays[r] : kLeagueDays[r], r, 2};
                ((push_row_fn)kPushRowFn)(rows, &row);
            }
            return;
        }
    }
    g_rows_orig(comp, rows, flag);
}

// Entry hook: the first `len` bytes (whole instructions, no RIP-relative
// operand) move to a trampoline that jumps back; the entry jumps to `handler`.
static void* hook_entry(uintptr_t fn, const unsigned char* sig, uint32_t len, void* handler) {
    if (!same_bytes(fn, sig, len)) return NULL;
    unsigned char* tramp = (unsigned char*)VirtualAlloc(NULL, 0x1000, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!tramp) return NULL;
    CopyMemory(tramp, (const void*)fn, len);
    absolute_jump(tramp + len, fn + len);
    FlushInstructionCache(GetCurrentProcess(), tramp, len + 14);
    unsigned char patch[32];
    for (uint32_t i = 0; i < len; ++i) patch[i] = 0x90;
    absolute_jump(patch, (uintptr_t)handler);
    if (!write_code(fn, patch, len)) {
        write_code(fn, sig, len);
        VirtualFree(tramp, 0, MEM_RELEASE);
        return NULL;
    }
    return tramp;
}

static void install_league36() {
    g_seed_orig = (seed_fn)hook_entry(kSeedFn, kSeedSig, sizeof(kSeedSig), (void*)&euro_seed);
    log_line(g_seed_orig ? "PATCHED seeding hook (36-club entrants)" : "ABORT seeding hook: prologue differs");
    g_rows_orig = (rows_fn)hook_entry(kRowsFn, kRowsSig, sizeof(kRowsSig), (void*)&euro_rows);
    log_line(g_rows_orig ? "PATCHED date rows hook (league phase 19/1 and 27/1)" : "ABORT date rows hook: prologue differs");
}

static void pin_self() {
    HMODULE self = NULL;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_PIN | GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
        (LPCWSTR)&euro_advance, &self);
}

enum { EURO_OK = 0, EURO_BASE = 1, EURO_NO_C41 = 2, EURO_C41_SIG = 3, EURO_SORT = 4,
       EURO_ADVANCE = 5, EURO_ALREADY = 6 };

static bool g_installed = false;

extern "C" __declspec(dllexport) int euro_rules_install(void) {
    if (!g_log_ready) { InitializeCriticalSection(&g_log_lock); g_log_ready = true; }
    log_line("LOADED euro_rules 1.3.0 (UEFA 2024+ knockout, 36-club league phase UCL+UEL, UEL on Thursdays, UEL final 26/5)");
    if (g_installed) return EURO_ALREADY;
    if ((uintptr_t)GetModuleHandleW(NULL) != kImageBase) { log_line("ABORT unexpected base"); return EURO_BASE; }
    g_c41 = (uint8_t*)GetModuleHandleA("ucl32_c41.dll");
    if (!g_c41) { log_line("ABORT ucl32_c41.dll is not loaded"); return EURO_NO_C41; }
    if (!same_bytes((uintptr_t)g_c41 + kC41Sort, kC41SortSig, sizeof(kC41SortSig))) {
        log_line("ABORT ucl32_c41 sort_table differs from C.4.1");
        return EURO_C41_SIG;
    }
    unsigned char jump[14];
    absolute_jump(jump, (uintptr_t)&euro_sort);
    if (!write_code((uintptr_t)g_c41 + kC41Sort, jump, sizeof(jump))) {
        write_code((uintptr_t)g_c41 + kC41Sort, kC41SortSig, sizeof(jump));
        log_line("ABORT sort patch readback differs");
        return EURO_SORT;
    }
    log_line("PATCHED c41 sort_table -> Article 18.01 ranking + 2025/26 bracket");
    pin_self();
    g_installed = true;
    real_dates();
    install_league36();
    if (!hook_advance()) return EURO_ADVANCE;
    log_line("INSTALLED");
    return EURO_OK;
}

BOOL APIENTRY DllMain(HMODULE mod, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(mod);
    return TRUE;
}
