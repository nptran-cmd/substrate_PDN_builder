; =============================================================================
; File: surface_bump_router_batch.il
; Package: agent04_pdn_architect
; Description: Layer 1 (SURFACE / TOP) Parameterized Bump-Via & Trace-Ganging
;              SKILL Router for Cadence Allegro / APD (.mcm).
;
;              Provides two high-speed O(N) execution modes:
;                1. pdn_import_surface_recipe_batch():
;                     Streams a Python-generated pipe-delimited SURFACE recipe
;                     from axlGetVariable("cwd") using makeTable O(1) lookup:
;                       VIA|<net>|<padstack>|SURFACE|12F|<x>|<y>
;                       CLINE|<net>|SURFACE|<width>|<x1>|<y1>|<x2>|<y2>
;                2. pdn_route_surface_refdes_by_ratio(refdes vdd_net vss_net ratio_str dir_str w_um):
;                     Directly routes a target RefDes (e.g. "U7") in SKILL for
;                     any ratio ("FULL", "4:2", "5:2", "M:N") and direction
;                     ("VERTICAL", "HORIZONTAL", "BOTH") using makeTable
;                     column/row hash tables.
; =============================================================================

procedure( pdn_resolve_surface_subclass()
    let((subs found s)
        subs = axlSubclasses("CONDUCTOR")
        found = "SURFACE"
        foreach(s subs
            if( upperCase(s) == "SURFACE" || upperCase(s) == "TOP" then
                found = s
            )
        )
        strcat("CONDUCTOR/" found)
    )
)

procedure( pdn_parse_ratio_pair(ratio_str)
    let((u parts m_vdd n_vss period_p)
        u = upperCase(ratio_str)
        if( u == "FULL" || u == "1:1" || u == "100%" then
            list(t 6 6 6)
        else
            parts = parseString(u ":")
            if( length(parts) >= 2 then
                m_vdd = atoi(car(parts))
                n_vss = atoi(cadr(parts))
            else
                m_vdd = 4
                n_vss = 2
            )
            if( m_vdd < 1 then m_vdd = 1)
            if( n_vss < 1 then n_vss = 1)
            period_p = 6
            if( m_vdd + 1 > period_p then period_p = m_vdd + 1)
            if( n_vss + 1 > period_p then period_p = n_vss + 1)
            list(nil m_vdd n_vss period_p)
        )
    )
)

procedure( pdn_is_index_kept_in_cell(idx count_keep period_p)
    let((mod_i kept_flag k cand)
        mod_i = mod(idx period_p)
        if( count_keep >= period_p then
            t
        else
            if( period_p == 6 then
                case( count_keep
                    (5 (mod_i == 0 || mod_i == 1 || mod_i == 2 || mod_i == 3 || mod_i == 4))
                    (4 (mod_i == 0 || mod_i == 1 || mod_i == 3 || mod_i == 4))
                    (3 (mod_i == 0 || mod_i == 2 || mod_i == 4))
                    (2 (mod_i == 1 || mod_i == 4))
                    (1 (mod_i == 2))
                    (t t)
                )
            else
                kept_flag = nil
                for(k 0 (count_keep - 1)
                    cand = round(((k + 0.5) * float(period_p) / float(count_keep)) - 0.5)
                    if( cand == mod_i then kept_flag = t)
                )
                kept_flag
            )
        )
    )
)

procedure( pdn_create_surface_cline(surf_layer net_dbid w_um x1 y1 x2 y2)
    let((path)
        path = axlPathStart(list(list(float(x1) float(y1))) float(w_um))
        axlPathLine(path float(w_um) list(float(x2) float(y2)))
        if( net_dbid != nil then
            axlDBCreatePath(path surf_layer net_dbid)
        else
            axlDBCreatePath(path surf_layer)
        )
    )
)

procedure( pdn_import_surface_recipe_batch()
    let((cwd recipe_path report_path save_design in_port line tokens rec_type
         net_tbl pad_tbl surf_layer default_via_ps
         via_cnt cline_cnt err_cnt
         net_name net_dbid ps_name vx vy w_um x1 y1 x2 y2)

        cwd = pdn_get_cwd()
        recipe_path = pdn_get_env("PDN_SURFACE_RECIPE" strcat(cwd "/mockup_L1_SURFACE_Ex3_5to2_recipe.txt"))
        report_path = pdn_get_env("PDN_REPORT_FILE" strcat(cwd "/surface_router_report.txt"))
        save_design = pdn_get_env_bool("PDN_SAVE_DESIGN" nil)

        errset(axlDBControl('drcEnable nil) nil)
        errset(axlDBControl('dynamicFillMode 'disabled) nil)

        net_tbl = pdn_ensure_net_table()
        pad_tbl = makeTable("pdn_surf_pad_tbl" nil)
        surf_layer = pdn_resolve_surface_subclass()
        default_via_ps = pdn_resolve_padstack(
            list("V77_49_77_SURFACE_12F_01A" "V77_49_77_01B_L01_L03" "V90_65_90_01A_L09_L10")
        )

        via_cnt = 0
        cline_cnt = 0
        err_cnt = 0

        in_port = infile(recipe_path)
        if( in_port == nil then
            pdn_write_report(
                report_path
                "ERROR"
                list(
                    list("STAGE" "SURFACE_LAYER1_ROUTER")
                    list("MESSAGE" strcat("Cannot open recipe file: " recipe_path))
                )
            )
            nil
        else
            while( gets(line in_port)
                line = car(parseString(line "\r\n"))
                if( line != nil && line != "" && substring(line 1 1) != "#" then
                    tokens = parseString(line "|")
                    if( length(tokens) >= 7 then
                        rec_type = upperCase(car(tokens))
                        case( rec_type
                            ("VIA"
                                ; Format: VIA|<net>|<padstack>|SURFACE|12F|<x>|<y>
                                net_name = nth(1 tokens)
                                ps_name  = nth(2 tokens)
                                vx       = float(atof(nth(5 tokens)))
                                vy       = float(atof(nth(6 tokens)))
                                if( pad_tbl[ps_name] == nil then
                                    if( axlLoadPadstack(ps_name) != nil then
                                        pad_tbl[ps_name] = ps_name
                                    else
                                        pad_tbl[ps_name] = default_via_ps
                                    )
                                )
                                net_dbid = pdn_get_or_create_net(net_tbl net_name)
                                if( pad_tbl[ps_name] != nil then
                                    if( net_dbid != nil then
                                        axlDBCreateVia(pad_tbl[ps_name] list(vx vy) net_dbid)
                                    else
                                        axlDBCreateVia(pad_tbl[ps_name] list(vx vy))
                                    )
                                    via_cnt = via_cnt + 1
                                else
                                    err_cnt = err_cnt + 1
                                )
                            )
                            ("CLINE"
                                ; Format: CLINE|<net>|SURFACE|<width>|<x1>|<y1>|<x2>|<y2>
                                if( length(tokens) >= 8 then
                                    net_name = nth(1 tokens)
                                    w_um     = float(atof(nth(3 tokens)))
                                    x1       = float(atof(nth(4 tokens)))
                                    y1       = float(atof(nth(5 tokens)))
                                    x2       = float(atof(nth(6 tokens)))
                                    y2       = float(atof(nth(7 tokens)))
                                    net_dbid = pdn_get_or_create_net(net_tbl net_name)
                                    pdn_create_surface_cline(surf_layer net_dbid w_um x1 y1 x2 y2)
                                    cline_cnt = cline_cnt + 1
                                )
                            )
                        )
                    )
                )
            )
            close(in_port)

            if( save_design then
                axlSaveDesign(?design axlCurrentDesign() ?noConfirm t)
            )

            pdn_write_report(
                report_path
                "SUCCESS"
                list(
                    list("STAGE" "SURFACE_LAYER1_ROUTER")
                    list("RECIPE_FILE" recipe_path)
                    list("SURFACE_LAYER" surf_layer)
                    list("VIAS_CREATED" sprintf(nil "%d" via_cnt))
                    list("CLINES_CREATED" sprintf(nil "%d" cline_cnt))
                    list("ERRORS" sprintf(nil "%d" err_cnt))
                )
            )
            printf("[AGENT04-SURFACE] Imported %d SURFACE->12F vias and %d SURFACE clines from %s.\n"
                via_cnt cline_cnt recipe_path)
            t
        )
    )
)

procedure( pdn_route_surface_refdes_by_ratio(
    refdes_name
    vdd_net_name
    vss_net_name
    ratio_str
    direction_str
    trace_w_um
)
    let((d syms target_sym pins pin pnet px py
         ratio_info is_full m_vdd n_vss period_p dir_u
         net_tbl surf_layer via_ps vdd_dbid vss_dbid
         vdd_bucket_tbl vss_bucket_tbl bkey
         via_cnt cline_cnt
         pts_list idx pt prev_via_pt)

        d = axlDBGetDesign()
        net_tbl = pdn_ensure_net_table()
        surf_layer = pdn_resolve_surface_subclass()
        via_ps = pdn_resolve_padstack(
            list("V77_49_77_SURFACE_12F_01A" "V77_49_77_01B_L01_L03")
        )
        vdd_dbid = pdn_get_or_create_net(net_tbl vdd_net_name)
        vss_dbid = pdn_get_or_create_net(net_tbl vss_net_name)

        ratio_info = pdn_parse_ratio_pair(ratio_str)
        is_full  = nth(0 ratio_info)
        m_vdd    = nth(1 ratio_info)
        n_vss    = nth(2 ratio_info)
        period_p = nth(3 ratio_info)
        dir_u    = upperCase(direction_str)

        vdd_bucket_tbl = makeTable("pdn_vdd_buckets" nil)
        vss_bucket_tbl = makeTable("pdn_vss_buckets" nil)

        target_sym = nil
        if( d != nil then
            foreach(sym d->symbols
                if( sym->refdes == refdes_name then
                    target_sym = sym
                )
            )
        )

        via_cnt = 0
        cline_cnt = 0

        if( target_sym != nil then
            pins = target_sym->pins
            foreach(pin pins
                pnet = if( pin->net != nil && pin->net->name != nil then pin->net->name else "")
                px = if( pin->xy != nil then float(car(pin->xy)) else 0.0)
                py = if( pin->xy != nil then float(cadr(pin->xy)) else 0.0)
                bkey = if( dir_u == "HORIZONTAL" then round(py / 5.0) else round(px / 5.0))
                if( upperCase(pnet) == upperCase(vdd_net_name) then
                    vdd_bucket_tbl[bkey] = cons(list(px py) vdd_bucket_tbl[bkey])
                else
                    if( upperCase(pnet) == upperCase(vss_net_name) then
                        vss_bucket_tbl[bkey] = cons(list(px py) vss_bucket_tbl[bkey])
                    )
                )
            )

            ; Route VDD buckets
            foreach(bk vdd_bucket_tbl
                pts_list = vdd_bucket_tbl[bk]
                idx = 0
                prev_via_pt = nil
                foreach(pt pts_list
                    if( is_full || pdn_is_index_kept_in_cell(idx m_vdd period_p) then
                        axlDBCreateVia(via_ps pt vdd_dbid)
                        via_cnt = via_cnt + 1
                        prev_via_pt = pt
                    else
                        if( prev_via_pt != nil then
                            pdn_create_surface_cline(
                                surf_layer vdd_dbid trace_w_um
                                car(pt) cadr(pt) car(prev_via_pt) cadr(prev_via_pt)
                            )
                            cline_cnt = cline_cnt + 1
                        else
                            axlDBCreateVia(via_ps pt vdd_dbid)
                            via_cnt = via_cnt + 1
                            prev_via_pt = pt
                        )
                    )
                    idx = idx + 1
                )
            )

            ; Route VSS buckets
            foreach(bk vss_bucket_tbl
                pts_list = vss_bucket_tbl[bk]
                idx = 0
                prev_via_pt = nil
                foreach(pt pts_list
                    if( is_full || pdn_is_index_kept_in_cell(idx n_vss period_p) then
                        axlDBCreateVia(via_ps pt vss_dbid)
                        via_cnt = via_cnt + 1
                        prev_via_pt = pt
                    else
                        if( prev_via_pt != nil then
                            pdn_create_surface_cline(
                                surf_layer vss_dbid trace_w_um
                                car(pt) cadr(pt) car(prev_via_pt) cadr(prev_via_pt)
                            )
                            cline_cnt = cline_cnt + 1
                        else
                            axlDBCreateVia(via_ps pt vss_dbid)
                            via_cnt = via_cnt + 1
                            prev_via_pt = pt
                        )
                    )
                    idx = idx + 1
                )
            )
        )

        printf("[AGENT04-SURFACE] Routed %s (%s/%s, ratio=%s, dir=%s): %d vias, %d clines.\n"
            refdes_name vdd_net_name vss_net_name ratio_str dir_u via_cnt cline_cnt)
        list(via_cnt cline_cnt)
    )
)
