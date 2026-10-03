// ucl32_format.cpp -- regenerador permanente de la fase liga UCL 32x6.
//
// Se engancha al planificador nativo de una competicion. Justo antes de que
// PES inserte en Calendar los eventos de la UCL (competition id *x400 + 3),
// sustituye solamente home/away de sus 96 Event ya creados. De este modo el
// mismo camino se ejecuta al crear una LM, al cargar una fase aun no jugada y
// al materializar la UCL de cada temporada posterior.
//
// Guardas duras:
//   * FL_2026.exe debe tener la base y la firma verificadas;
//   * deben existir exactamente 96 eventos, 16 por jornada y 32 clubes;
//   * todos deben estar pendientes o el fixture ya debe ser 6-rivales/3H/3A;
//   * todos los clubes deben tener pais conocido;
//   * la relectura debe cumplir todas las invariantes, o se hace rollback.
//
// No modifica el EXE ni ningun save en disco. El propio juego serializa los
// Event/Calendar al guardar la LM.

#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>

static const uintptr_t kImageBase = 0x140000000ULL;
static const uintptr_t kGlobalRootPtr = kImageBase + 0x03705E10;
static const uintptr_t kModelOffset = 0x48;
static const uintptr_t kEvents = 0x00E9FF08;
static const uint32_t kEventStride = 0x254;
static const uint32_t kEventCapacity = 0x32C8;
static const uintptr_t kCalendar = 0x016038A8;
static const uintptr_t kCalendarYear = 0x3F176;

static const uint32_t kEvId = 0x00;
static const uint32_t kEvPacked = 0x04;
static const uint32_t kEvHome = 0x14;
static const uint32_t kEvAway = 0x18;
static const uint32_t kEvPlayedBit = 0x40000000;
static const uint32_t kStageMask = 0x3FF;
static const uint32_t kStageUclGroup = 3;

// sub_01350B40(ctx, competition_id): planifica una competicion en Calendar.
// Copiamos 19 bytes completos antes del primer RIP-relative del prologo.
static const uintptr_t kSchedule = kImageBase + 0x01350B40;
static const uint32_t kSchedulePatchSize = 19;
static const unsigned char kScheduleSig[kSchedulePatchSize] = {
    0x48,0x8B,0xC4, 0x57, 0x41,0x54, 0x41,0x55, 0x41,0x56, 0x41,0x57,
    0x48,0x81,0xEC,0x80,0x00,0x00,0x00
};

static const char kLogName[] = "ucl32_format.log";

static CRITICAL_SECTION g_log_lock;
static bool g_log_ready = false;
static SRWLOCK g_country_lock = SRWLOCK_INIT;

struct CountryOverride { uint32_t team; uint16_t country; };
static CountryOverride g_country_overrides[1024];
static uint32_t g_country_override_count = 0;

static void log_line(const char* text) {
    SYSTEMTIME st;
    GetLocalTime(&st);
    char line[768];
    int n = wsprintfA(line, "%02u:%02u:%02u | %s\r\n",
        (unsigned)st.wHour, (unsigned)st.wMinute, (unsigned)st.wSecond, text);
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

static inline uint16_t rd16(uintptr_t a) { return *(const uint16_t*)a; }
static inline uint32_t rd32(uintptr_t a) { return *(const uint32_t*)a; }
static inline uintptr_t rdptr(uintptr_t a) { return *(const uintptr_t*)a; }
static inline uint32_t team_of(uint32_t encoded) { return (encoded >> 14) & 0x1FFFF; }

static uintptr_t model_base() {
    if (!readable((const void*)kGlobalRootPtr, sizeof(uintptr_t))) return 0;
    uintptr_t root = rdptr(kGlobalRootPtr);
    if (!readable((const void*)(root + kModelOffset), sizeof(uintptr_t))) return 0;
    uintptr_t model = rdptr(root + kModelOffset);
    if (!readable((const void*)(model + kEvents), kEventStride)) return 0;
    return model;
}

struct EventRef {
    uintptr_t addr;
    uint16_t id;
    uint8_t round;
    uint32_t old_home;
    uint32_t old_away;
};

struct DrawTeam {
    uint32_t encoded;
    uint32_t id;
    uint16_t country;
};

struct FixtureEdge {
    uint8_t a;
    uint8_t b;
    uint8_t home;
    uint8_t away;
    uint8_t round;
};

struct StaticCountry { uint32_t team; uint16_t country; };

// Respaldo para clubes de "Other Europe" y para los equipos prioritarios de
// FL26. Los clubes de ligas jugables se resuelven dinamicamente desde sus
// propios eventos de liga; esta tabla cubre los casos sin liga nacional propia.
static const StaticCountry kStaticCountries[] = {
    {101,17},{102,17},{103,17},{105,17},{106,17},{107,17},{108,19},{109,19},
    {110,19},{112,20},{113,20},{114,20},{116,21},{117,21},{118,21},{119,18},
    {120,18},{121,18},{122,18},{124,18},{125,18},{126,50},{127,50},{128,50},
    {130,118},{131,133},{132,133},{133,117},{172,19},{173,17},{177,17},{179,17},
    {181,20},{191,22},{192,22},{193,22},{194,19},{196,19},{197,118},{213,20},
    {226,50},{231,50},{234,18},{258,19},{265,19},{267,19},{269,115},{270,117},
    {198,117},{327,18},{377,17},{1207,141},{1208,141},{1218,116},{1223,203},
    {1706,201},{1753,116},{1950,201},{2618,116},{5010,50},{5189,202},
    {5194,115},{5220,115},{5253,204},{5973,19}
};

static bool is_domestic_league(uint16_t stage) {
    static const uint16_t ids[] = {
        17,18,19,20,21,22,50,79,80,81,82,99,115,116,117,118,133,141,162
    };
    for (uint32_t i = 0; i < sizeof(ids)/sizeof(ids[0]); ++i)
        if (ids[i] == stage) return true;
    return false;
}

static uint16_t canonical_country(uint16_t stage) {
    // Las segundas divisiones pertenecen al mismo pais que su primera liga.
    if (stage == 79) return 17;
    if (stage == 80) return 19;
    if (stage == 81) return 20;
    if (stage == 82) return 18;
    return stage;
}

static uint16_t static_country(uint32_t team) {
    for (uint32_t i = 0; i < sizeof(kStaticCountries)/sizeof(kStaticCountries[0]); ++i)
        if (kStaticCountries[i].team == team) return kStaticCountries[i].country;
    return 0;
}

static uint16_t override_country(uint32_t team) {
    uint16_t country = 0;
    AcquireSRWLockShared(&g_country_lock);
    for (uint32_t i = 0; i < g_country_override_count; ++i) {
        if (g_country_overrides[i].team == team) {
            country = g_country_overrides[i].country;
            break;
        }
    }
    ReleaseSRWLockShared(&g_country_lock);
    return country;
}

static uint16_t country_from_events(uintptr_t model, uint32_t team) {
    uint16_t supplied = override_country(team);
    if (supplied) return supplied;
    uintptr_t events = model + kEvents;
    uint16_t found = 0;
    for (uint32_t eid = 0; eid < kEventCapacity; ++eid) {
        uintptr_t ev = events + (uintptr_t)eid * kEventStride;
        if (rd16(ev + kEvId) != (uint16_t)eid) continue;
        uint16_t stage = (uint16_t)(rd32(ev + kEvPacked) & kStageMask);
        if (!is_domestic_league(stage) || stage == 99) continue;
        uint32_t home = team_of(rd32(ev + kEvHome));
        uint32_t away = team_of(rd32(ev + kEvAway));
        if (home != team && away != team) continue;
        uint16_t country = canonical_country(stage);
        if (found && found != country) return 0;
        found = country;
    }
    return found ? found : static_country(team);
}

static void sort_events(EventRef* refs, uint32_t n) {
    for (uint32_t i = 1; i < n; ++i) {
        EventRef v = refs[i];
        uint32_t j = i;
        while (j && (refs[j-1].round > v.round ||
            (refs[j-1].round == v.round && refs[j-1].id > v.id))) {
            refs[j] = refs[j-1]; --j;
        }
        refs[j] = v;
    }
}

static bool collect_fixture(uintptr_t model, EventRef* refs, DrawTeam* teams,
                            uint32_t* played_out) {
    uint32_t nrefs = 0, nteams = 0, played = 0;
    uint32_t per_round[6] = {0,0,0,0,0,0};
    uintptr_t events = model + kEvents;
    for (uint32_t eid = 0; eid < kEventCapacity; ++eid) {
        uintptr_t ev = events + (uintptr_t)eid * kEventStride;
        if (rd16(ev + kEvId) != (uint16_t)eid) continue;
        uint32_t packed = rd32(ev + kEvPacked);
        if ((packed & kStageMask) != kStageUclGroup) continue;
        uint32_t round = (packed >> 16) & 0xFFF;
        if (round >= 6 || nrefs >= 96) return false;
        uint32_t sides[2] = {rd32(ev + kEvHome), rd32(ev + kEvAway)};
        if (!team_of(sides[0]) || !team_of(sides[1]) || team_of(sides[0]) == team_of(sides[1]))
            return false;
        refs[nrefs++] = {(uintptr_t)ev,(uint16_t)eid,(uint8_t)round,sides[0],sides[1]};
        per_round[round]++;
        if (packed & kEvPlayedBit) played++;
        for (uint32_t s = 0; s < 2; ++s) {
            uint32_t id = team_of(sides[s]), i = 0;
            for (; i < nteams; ++i) if (teams[i].id == id) break;
            if (i == nteams) {
                if (nteams >= 32) return false;
                teams[nteams++] = {sides[s],id,0};
            } else if (teams[i].encoded != sides[s]) return false;
        }
    }
    if (nrefs != 96 || nteams != 32) return false;
    for (uint32_t r = 0; r < 6; ++r) if (per_round[r] != 16) return false;
    for (uint32_t i = 1; i < nteams; ++i) {
        DrawTeam v = teams[i]; uint32_t j = i;
        while (j && teams[j-1].id > v.id) { teams[j] = teams[j-1]; --j; }
        teams[j] = v;
    }
    sort_events(refs, nrefs);
    *played_out = played;
    return true;
}

static int team_index(const DrawTeam* teams, uint32_t encoded) {
    uint32_t id = team_of(encoded);
    for (int i = 0; i < 32; ++i) if (teams[i].id == id) return i;
    return -1;
}

static bool validate_current(const EventRef* refs, const DrawTeam* teams,
                             bool require_country) {
    uint8_t app[32] = {0}, home[32] = {0}, away[32] = {0};
    bool seen[32][32] = {};
    for (uint32_t base = 0; base < 96; base += 16) {
        bool used[32] = {};
        for (uint32_t k = 0; k < 16; ++k) {
            int h = team_index(teams, rd32(refs[base+k].addr + kEvHome));
            int a = team_index(teams, rd32(refs[base+k].addr + kEvAway));
            if (h < 0 || a < 0 || h == a || used[h] || used[a] || seen[h][a]) return false;
            if (require_country && teams[h].country == teams[a].country) return false;
            used[h] = used[a] = true; seen[h][a] = seen[a][h] = true;
            app[h]++; app[a]++; home[h]++; away[a]++;
        }
    }
    for (uint32_t i = 0; i < 32; ++i)
        if (app[i] != 6 || home[i] != 3 || away[i] != 3) return false;
    return true;
}

static uint32_t rng_next(uint32_t* state) {
    uint32_t x = *state;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    return *state = x ? x : 0x9E3779B9u;
}

static bool build_draw(DrawTeam* teams, uint16_t year, FixtureEdge* edges) {
    uint32_t seed = 0xA341316Cu ^ year;
    for (uint32_t i = 0; i < 32; ++i) seed = (seed * 16777619u) ^ teams[i].id;
    uint8_t order[32];
    for (uint32_t attempt = 0; attempt < 4096; ++attempt) {
        for (uint8_t i = 0; i < 32; ++i) order[i] = i;
        uint32_t state = seed ^ (attempt * 0x9E3779B9u);
        for (uint32_t i = 31; i; --i) {
            uint32_t j = rng_next(&state) % (i + 1);
            uint8_t t = order[i]; order[i] = order[j]; order[j] = t;
        }
        uint8_t rotation[32];
        for (uint32_t i = 0; i < 32; ++i) rotation[i] = order[i];
        uint32_t selected = 0;
        for (uint32_t rr = 0; rr < 31 && selected < 6; ++rr) {
            bool clean = true;
            for (uint32_t k = 0; k < 16; ++k) {
                uint8_t a = rotation[k], b = rotation[31-k];
                if (teams[a].country == teams[b].country) { clean = false; break; }
            }
            if (clean) {
                for (uint32_t k = 0; k < 16; ++k) {
                    FixtureEdge& e = edges[selected*16+k];
                    e.a = rotation[k]; e.b = rotation[31-k]; e.round = (uint8_t)selected;
                    e.home = e.away = 0xFF;
                }
                selected++;
            }
            uint8_t last = rotation[31];
            for (uint32_t i = 31; i > 1; --i) rotation[i] = rotation[i-1];
            rotation[1] = last;
        }
        if (selected != 6) continue;

        // Orientacion euleriana: el grafo es 6-regular, por lo que cada club
        // termina con exactamente tres salidas (local) y tres entradas.
        bool used_edge[96] = {};
        for (uint8_t start = 0; start < 32; ++start) {
            bool pending = false;
            for (uint32_t e = 0; e < 96; ++e)
                if (!used_edge[e] && (edges[e].a == start || edges[e].b == start)) { pending = true; break; }
            if (!pending) continue;
            uint8_t stack[98]; uint32_t sp = 0; stack[sp++] = start;
            while (sp) {
                uint8_t v = stack[sp-1]; int found = -1;
                for (uint32_t e = 0; e < 96; ++e)
                    if (!used_edge[e] && (edges[e].a == v || edges[e].b == v)) { found = (int)e; break; }
                if (found < 0) { --sp; continue; }
                FixtureEdge& edge = edges[found];
                uint8_t next = edge.a == v ? edge.b : edge.a;
                used_edge[found] = true; edge.home = v; edge.away = next;
                stack[sp++] = next;
            }
        }
        bool ok = true; uint8_t homes[32] = {0};
        for (uint32_t e = 0; e < 96; ++e) {
            if (edges[e].home == 0xFF) ok = false;
            else homes[edges[e].home]++;
        }
        for (uint32_t i = 0; i < 32; ++i) if (homes[i] != 3) ok = false;
        if (ok) return true;
    }
    return false;
}

static volatile LONG g_format_inside = 0;
static uint32_t g_last_signature = 0;

static void apply_format_if_needed() {
    if (InterlockedCompareExchange(&g_format_inside, 1, 0) != 0) return;
    uintptr_t model = model_base();
    if (!model) { InterlockedExchange(&g_format_inside, 0); return; }
    EventRef refs[96]; DrawTeam teams[32]; uint32_t played = 0;
    if (!collect_fixture(model, refs, teams, &played)) {
        log_line("FORMAT-BLOCKED estructura UCL distinta de 96/32/6x16");
        InterlockedExchange(&g_format_inside, 0); return;
    }
    uint16_t year = readable((const void*)(model+kCalendar+kCalendarYear),2)
        ? rd16(model+kCalendar+kCalendarYear) : 0;
    uint32_t signature = year;
    for (uint32_t i = 0; i < 32; ++i) signature = signature*16777619u ^ teams[i].id;
    for (uint32_t i = 0; i < 32; ++i) {
        teams[i].country = country_from_events(model, teams[i].id);
        if (!teams[i].country) {
            char msg[160]; wsprintfA(msg,"FORMAT-BLOCKED pais desconocido para team %u",teams[i].id);
            log_line(msg); g_last_signature = signature;
            InterlockedExchange(&g_format_inside, 0); return;
        }
    }
    if (validate_current(refs, teams, true)) {
        if (g_last_signature != signature) log_line("FORMAT-OK fixture 32x6 ya presente; no se reescribe");
        g_last_signature = signature;
        InterlockedExchange(&g_format_inside, 0); return;
    }
    if (played) {
        if (g_last_signature != signature) log_line("FORMAT-BLOCKED hay partidos UCL jugados; se preserva la temporada");
        g_last_signature = signature;
        InterlockedExchange(&g_format_inside, 0); return;
    }
    FixtureEdge edges[96];
    if (!build_draw(teams, year, edges)) {
        log_line("FORMAT-BLOCKED no existe sorteo compatible sin cruces del mismo pais");
        g_last_signature = signature;
        InterlockedExchange(&g_format_inside, 0); return;
    }
    for (uint32_t i = 0; i < 96; ++i) {
        *(uint32_t*)(refs[i].addr+kEvHome) = teams[edges[i].home].encoded;
        *(uint32_t*)(refs[i].addr+kEvAway) = teams[edges[i].away].encoded;
    }
    if (!validate_current(refs, teams, true)) {
        for (uint32_t i = 0; i < 96; ++i) {
            *(uint32_t*)(refs[i].addr+kEvHome) = refs[i].old_home;
            *(uint32_t*)(refs[i].addr+kEvAway) = refs[i].old_away;
        }
        log_line("FORMAT-ROLLBACK fallo de relectura; restaurados los 96 eventos");
    } else {
        char msg[192]; wsprintfA(msg,"FORMAT-APPLIED temporada %u: 32 equipos, 96 partidos, 6 rivales, 3H/3A, 0 mismo pais",year);
        log_line(msg); g_last_signature = signature;
    }
    InterlockedExchange(&g_format_inside, 0);
}

typedef void (*schedule_fn)(void*, unsigned short);
static schedule_fn g_original_schedule = NULL;
static unsigned char g_original_bytes[kSchedulePatchSize];
static void* g_trampoline = NULL;
static bool g_installed = false;

static void ucl32_schedule_hook(void* ctx, unsigned short comp_id) {
    if ((comp_id & kStageMask) == kStageUclGroup) apply_format_if_needed();
    g_original_schedule(ctx, comp_id);
}

static bool same_bytes(uintptr_t addr, const unsigned char* want, uint32_t n) {
    for (uint32_t i = 0; i < n; ++i) if (*(const unsigned char*)(addr+i) != want[i]) return false;
    return true;
}

static void pin_self() {
    HMODULE self = NULL;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_PIN|GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
        (LPCWSTR)&ucl32_schedule_hook, &self);
}

enum { FORMAT_OK=0, FORMAT_BASE=1, FORMAT_SIG=2, FORMAT_ALLOC=3,
       FORMAT_PROTECT=4, FORMAT_READBACK=5, FORMAT_ALREADY=6 };

// JMP [RIP+0] seguido del destino: no destruye RAX ni ningun otro registro.
// El prologo conserva RSP en RAX y la continuacion escribe en [RAX-0x58].
static void write_absolute_jump(unsigned char* out, uintptr_t target) {
    out[0] = 0xFF; out[1] = 0x25;
    out[2] = out[3] = out[4] = out[5] = 0;
    for (uint32_t i = 0; i < 8; ++i)
        out[6+i] = (unsigned char)(target >> (i*8));
}

extern "C" __declspec(dllexport) int ucl32_format_install(void) {
    if (!g_log_ready) { InitializeCriticalSection(&g_log_lock); g_log_ready = true; }
    log_line("LOADED ucl32 format permanente 1.1.1 (retorno conserva RAX)");
    if (g_installed) return FORMAT_ALREADY;
    if ((uintptr_t)GetModuleHandleW(NULL) != kImageBase) { log_line("ABORT base inesperada"); return FORMAT_BASE; }
    if (!same_bytes(kSchedule,kScheduleSig,kSchedulePatchSize)) { log_line("ABORT firma del planificador distinta"); return FORMAT_SIG; }

    g_trampoline = VirtualAlloc(NULL, 0x1000, MEM_RESERVE|MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!g_trampoline) return FORMAT_ALLOC;
    for (uint32_t i=0;i<kSchedulePatchSize;++i) {
        g_original_bytes[i]=*(const unsigned char*)(kSchedule+i);
        ((unsigned char*)g_trampoline)[i]=g_original_bytes[i];
    }
    unsigned char* t=(unsigned char*)g_trampoline+kSchedulePatchSize;
    write_absolute_jump(t, kSchedule+kSchedulePatchSize);
    FlushInstructionCache(GetCurrentProcess(), g_trampoline, kSchedulePatchSize+14);
    g_original_schedule=(schedule_fn)g_trampoline;

    unsigned char patch[kSchedulePatchSize];
    for (uint32_t i=0;i<kSchedulePatchSize;++i) patch[i]=0x90;
    write_absolute_jump(patch, (uintptr_t)&ucl32_schedule_hook);
    DWORD old=0;
    if (!VirtualProtect((void*)kSchedule,kSchedulePatchSize,PAGE_EXECUTE_READWRITE,&old)) return FORMAT_PROTECT;
    for (uint32_t i=0;i<kSchedulePatchSize;++i) *(volatile unsigned char*)(kSchedule+i)=patch[i];
    FlushInstructionCache(GetCurrentProcess(),(const void*)kSchedule,kSchedulePatchSize);
    DWORD ignored=0; VirtualProtect((void*)kSchedule,kSchedulePatchSize,old,&ignored);
    if (!same_bytes(kSchedule,patch,kSchedulePatchSize)) return FORMAT_READBACK;
    pin_self(); g_installed=true;
    log_line("INSTALLED hook de generacion por temporada en sub_01350B40");
    return FORMAT_OK;
}

// CommonLib extrae CompetitionEntry.bin antes de entrar a una LM. El loader
// entrega aqui su mapa completo de clubes de ligas jugables, evitando depender
// de que ya existan eventos domesticos en el modelo de la temporada.
extern "C" __declspec(dllexport) int ucl32_format_set_country(
        uint32_t team, uint16_t country) {
    if (!team || !country) return 1;
    int result = 0;
    AcquireSRWLockExclusive(&g_country_lock);
    uint32_t i = 0;
    for (; i < g_country_override_count; ++i) {
        if (g_country_overrides[i].team == team) {
            g_country_overrides[i].country = country;
            break;
        }
    }
    if (i == g_country_override_count) {
        if (g_country_override_count >=
                sizeof(g_country_overrides)/sizeof(g_country_overrides[0])) {
            result = 2;
        } else {
            g_country_overrides[g_country_override_count++] = {team, country};
        }
    }
    ReleaseSRWLockExclusive(&g_country_lock);
    return result;
}

extern "C" __declspec(dllexport) int ucl32_format_uninstall(void) {
    if (!g_installed) return FORMAT_OK;
    DWORD old=0;
    if (VirtualProtect((void*)kSchedule,kSchedulePatchSize,PAGE_EXECUTE_READWRITE,&old)) {
        for (uint32_t i=0;i<kSchedulePatchSize;++i) *(volatile unsigned char*)(kSchedule+i)=g_original_bytes[i];
        FlushInstructionCache(GetCurrentProcess(),(const void*)kSchedule,kSchedulePatchSize);
        DWORD ignored=0; VirtualProtect((void*)kSchedule,kSchedulePatchSize,old,&ignored);
    }
    g_installed=false; log_line("UNINSTALLED hook de formato"); return FORMAT_OK;
}

BOOL APIENTRY DllMain(HMODULE mod, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(mod);
    return TRUE;
}
