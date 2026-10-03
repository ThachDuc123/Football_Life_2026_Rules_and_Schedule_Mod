-- Permanent post-playoff calendar recovery for the validated FL26 build.
-- Self-contained: it does not depend on LM AI Director or other private mods.
-- Runs only when Sider exposes a Master League schedule, never from a match
-- callback. The worker rechecks and briefly suspends the game for atomic writes.
local m = { version = "1.2.0" }
local worker = nil
local next_check = 0
local runtime_dir
local python

if ffi ~= nil then
    ffi.cdef[[
        typedef struct {
            unsigned long cb; char* lpReserved; char* lpDesktop; char* lpTitle;
            unsigned long dwX; unsigned long dwY; unsigned long dwXSize;
            unsigned long dwYSize; unsigned long dwXCountChars;
            unsigned long dwYCountChars; unsigned long dwFillAttribute;
            unsigned long dwFlags; unsigned short wShowWindow;
            unsigned short cbReserved2; unsigned char* lpReserved2;
            void* hStdInput; void* hStdOutput; void* hStdError;
        } UCL32_STARTUPINFOA;
        typedef struct {
            void* hProcess; void* hThread; unsigned long dwProcessId;
            unsigned long dwThreadId;
        } UCL32_PROCESS_INFORMATION;
        void* GetModuleHandleA(const char* lpModuleName);
        void* GetProcAddress(void* hModule, const char* lpProcName);
        int CloseHandle(void* hObject);
        unsigned long GetLastError(void);
        unsigned long GetCurrentProcessId(void);
        unsigned long GetTickCount(void);
        int GetExitCodeProcess(void* hProcess, unsigned long* lpExitCode);
    ]]
end

function m.get_stadium_name(ctx, name, stadium, entry)
    if not entry or ffi == nil then return nil end
    if worker ~= nil then
        local code = ffi.new("unsigned long[1]")
        if ffi.C.GetExitCodeProcess(worker, code) == 0 or code[0] == 259 then
            return nil
        end
        ffi.C.CloseHandle(worker)
        worker = nil
        if code[0] ~= 0 then
            log("[ucl_calendar_guard] waiting: inspect calendar-status.json for precondition failure")
        end
    end
    local now = tonumber(ffi.C.GetTickCount())
    if now < next_check then return nil end
    next_check = now + 5000
    local command = '"' .. python .. '" "' .. runtime_dir ..
        '\\repair_ucl_calendar.py" --pid ' .. tostring(ffi.C.GetCurrentProcessId()) ..
        ' --ensure --apply --output "' .. runtime_dir .. '\\calendar-status.json"'
    local buffer = ffi.new("char[?]", #command + 1, command)
    local startup = ffi.new("UCL32_STARTUPINFOA[1]")
    local process = ffi.new("UCL32_PROCESS_INFORMATION[1]")
    startup[0].cb = ffi.sizeof(startup[0])
    local kernel = ffi.C.GetModuleHandleA("kernel32.dll")
    local entry = kernel ~= nil and ffi.C.GetProcAddress(kernel, "CreateProcessA") or nil
    if entry == nil then
        log("[ucl_calendar_guard] CreateProcessA unavailable")
        return nil
    end
    local create_process = ffi.cast(
        "int(*)(const char*,char*,void*,void*,int,unsigned long,void*,const char*,void*,void*)",
        entry)
    if create_process(python, buffer, nil, nil, 0, 0x08000000,
        nil, runtime_dir, ffi.cast("void*", startup), ffi.cast("void*", process)) == 0 then
        log("[ucl_calendar_guard] worker launch failed: " .. tostring(ffi.C.GetLastError()))
        return nil
    end
    ffi.C.CloseHandle(process[0].hThread)
    worker = process[0].hProcess
    return nil
end

function m.init(ctx)
    if ffi == nil then error("ucl_calendar_guard requires LuaJIT extensions") end
    runtime_dir = ctx.sider_dir:gsub("[\\/]+$", "") .. "\\content\\ucl_calendar_guard"
    local config = io.open(runtime_dir .. "\\python.txt", "r")
    if not config then error("ucl_calendar_guard: missing python.txt") end
    python = config:read("*l")
    config:close()
    local executable = io.open(python, "rb")
    if not executable then error("ucl_calendar_guard: Python runtime missing") end
    executable:close()
    ctx.register("get_stadium_name", m.get_stadium_name)
    ctx.register("livecpk_data_ready", m.data_ready)
    log("[ucl_calendar_guard] installed v" .. m.version ..
        ": UCL >=7 days, domestic rest >=3 days, final day149")
end

function m.data_ready(ctx, filename, data, len, total_size, offset)
    local name = string.lower(filename or "")
    if offset + len >= total_size and
       (name:match("\\schedule%.bin$") or name:match("\\rankinggroupleaguepes%.bin$")
        or name:match("\\modemainmenuml%.bin$")) then
        m.get_stadium_name(ctx, nil, nil, true)
    end
end

return m
