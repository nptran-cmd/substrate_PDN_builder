; =============================================================================
; File: pdn_core_batch.il
; Package: agent04_pdn_architect
; Description: Shared headless SKILL core library for Agent 04 (PDN Architect).
;              Provides env-var readers, O(1) SKILL makeTable pipe-delimited
;              file loaders, layer/padstack resolvers, and report writers.
; =============================================================================

procedure( pdn_get_env(var_name default_val)
    let((val)
        val = getShellEnvVar(var_name)
        if( val == nil || val == "" then
            val = axlGetVariable(var_name)
        )
        if( val == nil || val == "" then
            default_val
        else
            val
        )
    )
)

procedure( pdn_get_env_float(var_name default_val)
    let((s val)
        s = pdn_get_env(var_name "")
        if( s == "" then
            float(default_val)
        else
            val = atof(s)
            if( val == nil then float(default_val) else float(val))
        )
    )
)

procedure( pdn_get_env_int(var_name default_val)
    let((s val)
        s = pdn_get_env(var_name "")
        if( s == "" then
            default_val
        else
            val = atoi(s)
            if( val == nil then default_val else val)
        )
    )
)

procedure( pdn_get_env_bool(var_name default_val)
    let((s u)
        s = pdn_get_env(var_name "")
        if( s == "" then
            default_val
        else
            u = upperCase(s)
            if( u == "1" || u == "TRUE" || u == "YES" || u == "T" then
                t
            else
                nil
            )
        )
    )
)

procedure( pdn_parse_csv_list(csv_str)
    let((raw_list clean_list item)
        if( csv_str == nil || csv_str == "" then
            nil
        else
            raw_list = parseString(csv_str ",;")
            clean_list = nil
            foreach(item raw_list
                if( item != "" then
                    clean_list = append1(clean_list item)
                )
            )
            clean_list
        )
    )
)

procedure( pdn_get_cwd()
    let((cwd)
        cwd = getShellEnvVar("PDN_CWD")
        if( cwd == nil || cwd == "" then
            cwd = axlGetVariable("PDN_CWD")
        )
        if( cwd == nil || cwd == "" then
            cwd = axlGetVariable("cwd")
        )
        if( cwd == nil || cwd == "" then
            cwd = "."
        )
        cwd
    )
)

procedure( pdn_resolve_padstack(preferred_names)
    let((d ps_list found_name cand ps_obj)
        d = axlDBGetDesign()
        found_name = nil
        foreach(cand preferred_names
            if( found_name == nil && cand != nil && cand != "" then
                ps_obj = axlLoadPadstack(cand)
                if( ps_obj != nil then
                    found_name = cand
                )
            )
        )
        if( found_name == nil && d != nil then
            ps_list = d->padstacks
            if( ps_list != nil && length(ps_list) > 0 then
                found_name = car(ps_list)->name
            )
        )
        found_name
    )
)

procedure( pdn_resolve_conductor_subclass(target_sub)
    let((subs found_sub s u_target)
        u_target = upperCase(target_sub)
        subs = axlSubclasses("CONDUCTOR")
        found_sub = nil
        foreach(s subs
            if( found_sub == nil && upperCase(s) == u_target then
                found_sub = s
            )
        )
        if( found_sub == nil && subs != nil && length(subs) > 0 then
            if( u_target == "BASE" || u_target == "BOTTOM" then
                found_sub = car(last(subs))
            else
                found_sub = car(subs)
            )
        )
        found_sub
    )
)

procedure( pdn_ensure_net_table()
    let((d net_tbl n)
        d = axlDBGetDesign()
        net_tbl = makeTable("pdn_net_table" nil)
        if( d != nil then
            foreach(n d->nets
                if( n->name != nil then
                    net_tbl[n->name] = n
                    net_tbl[upperCase(n->name)] = n
                )
            )
        )
        net_tbl
    )
)

procedure( pdn_get_or_create_net(net_tbl net_name)
    let((n)
        if( net_name == nil || net_name == "" then
            nil
        else
            n = net_tbl[net_name]
            if( n == nil then
                n = net_tbl[upperCase(net_name)]
            )
            if( n == nil then
                n = axlDBCreateNet(net_name)
                if( n != nil then
                    net_tbl[net_name] = n
                    net_tbl[upperCase(net_name)] = n
                )
            )
            n
        )
    )
)

procedure( pdn_write_report(report_file status_str kv_list)
    let((p pair)
        p = outfile(report_file "w")
        if( p != nil then
            fprintf(p "STATUS=%s\n" status_str)
            foreach(pair kv_list
                fprintf(p "%s=%s\n" car(pair) cadr(pair))
            )
            close(p)
            t
        else
            nil
        )
    )
)
