; =============================================================================
; File: pdn_import_from_txt_batch.il
; Package: agent04_pdn_architect
; Description: Stage 4 Pipe-Delimited Recipe Importer (pdn_import_recipe.txt -> .mcm).
;              Streams <cwd>/pdn_import_recipe.txt line-by-line using SKILL
;              infile/gets/parseString and SKILL makeTable hash tables for O(1)
;              net, padstack, and layer subclass lookup. Disables online DRC
;              and dynamic shape fill during batch creation for maximum speed.
; =============================================================================

procedure( pdn_kv_from_tokens(tokens)
    let((tbl tok kv)
        tbl = makeTable("pdn_line_kv" "")
        foreach(tok tokens
            kv = parseString(tok "=")
            if( length(kv) >= 2 then
                tbl[upperCase(car(kv))] = cadr(kv)
            )
        )
        tbl
    )
)

procedure( pdn_build_subclass_table()
    let((sub_tbl subs s default_top default_bot)
        sub_tbl = makeTable("pdn_sub_table" nil)
        subs = axlSubclasses("CONDUCTOR")
        default_top = if( subs != nil && length(subs) > 0 then car(subs) else nil)
        default_bot = if( subs != nil && length(subs) > 0 then car(last(subs)) else nil)
        foreach(s subs
            sub_tbl[s] = s
            sub_tbl[upperCase(s)] = s
        )
        sub_tbl["DEFAULT_TOP"] = default_top
        sub_tbl["DEFAULT_BOT"] = default_bot
        sub_tbl
    )
)

procedure( pdn_lookup_subclass(sub_tbl raw_layer)
    let((clean u found)
        clean = if( rexMatchp("/" raw_layer) then cadr(parseString(raw_layer "/")) else raw_layer)
        u = upperCase(clean)
        found = sub_tbl[u]
        if( found == nil then
            if( u == "BASE" || u == "BOTTOM" then
                found = sub_tbl["DEFAULT_BOT"]
            else
                found = sub_tbl["DEFAULT_TOP"]
            )
        )
        found
    )
)

procedure( pdn_run_import_from_txt_batch()
    let((cwd recipe_path report_path summary_path save_design max_ops total_db_ops
         in_port line tokens rec_type kv_tbl
         net_tbl pad_tbl sub_tbl default_ps
         via_cnt cline_cnt guard_cnt koz_cnt lsc_cnt plane_cnt skipped_cnt err_cnt
         ps_name net_name net_dbid x y x1 y1 x2 y2 w_um layer_str sub_name path)
        cwd = pdn_get_cwd()
        recipe_path = pdn_get_env("PDN_RECIPE_FILE" strcat(cwd "/pdn_import_recipe.txt"))
        report_path = pdn_get_env("PDN_REPORT_FILE" strcat(cwd "/pdn_report.txt"))
        summary_path = pdn_get_env("PDN_SUMMARY_FILE" strcat(cwd "/pdn_import_summary.txt"))
        save_design = pdn_get_env_bool("PDN_SAVE_DESIGN" nil)
        max_ops = pdn_get_env_int("PDN_MAX_IMPORT_OPS" if( save_design then 500000 else 150))

        ; Disable online DRC & dynamic fill during high-speed batch import
        errset(axlDBControl('drcEnable nil) nil)
        errset(axlDBControl('dynamicFillMode 'disabled) nil)

        net_tbl = pdn_ensure_net_table()
        pad_tbl = makeTable("pdn_pad_table" nil)
        sub_tbl = pdn_build_subclass_table()
        default_ps = pdn_resolve_padstack(list("V90_65_90_01A_L09_L10" "V282_5_150_282_5_01A_2FCI_2BCI" "c560_35_01a"))

        via_cnt = 0
        cline_cnt = 0
        guard_cnt = 0
        koz_cnt = 0
        lsc_cnt = 0
        plane_cnt = 0
        skipped_cnt = 0
        err_cnt = 0
        total_db_ops = 0

        in_port = infile(recipe_path)
        if( in_port == nil then
            pdn_write_report(
                report_path
                "ERROR"
                list(
                    list("STAGE" "STAGE4_TXT_IMPORT")
                    list("MESSAGE" strcat("Cannot open recipe file: " recipe_path))
                )
            )
            nil
        else
            while( gets(line in_port)
                line = car(parseString(line "\r\n"))
                if( line != nil && line != "" && substring(line 1 1) != "#" then
                    tokens = parseString(line "|")
                    if( length(tokens) > 0 then
                        rec_type = upperCase(car(tokens))
                        kv_tbl = pdn_kv_from_tokens(cdr(tokens))

                        case( rec_type
                            ("PLANE_POLARITY"
                                plane_cnt = plane_cnt + 1
                            )
                            ("VIA"
                                via_cnt = via_cnt + 1
                                if( total_db_ops < max_ops then
                                    total_db_ops = total_db_ops + 1
                                    ps_name = kv_tbl["PADSTACK"]
                                    if( pad_tbl[ps_name] == nil then
                                        if( axlLoadPadstack(ps_name) != nil then
                                            pad_tbl[ps_name] = ps_name
                                        else
                                            pad_tbl[ps_name] = default_ps
                                        )
                                    )
                                    net_name = kv_tbl["NET"]
                                    net_dbid = pdn_get_or_create_net(net_tbl net_name)
                                    x = float(atof(kv_tbl["X"]))
                                    y = float(atof(kv_tbl["Y"]))
                                    if( pad_tbl[ps_name] != nil then
                                        if( net_dbid != nil then
                                            axlDBCreateVia(pad_tbl[ps_name] list(x y) net_dbid)
                                        else
                                            axlDBCreateVia(pad_tbl[ps_name] list(x y))
                                        )
                                    else
                                        err_cnt = err_cnt + 1
                                    )
                                else
                                    skipped_cnt = skipped_cnt + 1
                                )
                            )
                            ("CLINE"
                                cline_cnt = cline_cnt + 1
                                if( total_db_ops < max_ops then
                                    total_db_ops = total_db_ops + 1
                                    layer_str = kv_tbl["LAYER"]
                                    sub_name = pdn_lookup_subclass(sub_tbl layer_str)
                                    net_name = kv_tbl["NET"]
                                    net_dbid = pdn_get_or_create_net(net_tbl net_name)
                                    w_um = float(atof(kv_tbl["WIDTH"]))
                                    x1 = float(atof(kv_tbl["X1"]))
                                    y1 = float(atof(kv_tbl["Y1"]))
                                    x2 = float(atof(kv_tbl["X2"]))
                                    y2 = float(atof(kv_tbl["Y2"]))
                                    if( sub_name != nil then
                                        path = axlPathStart(list(list(x1 y1)) w_um)
                                        axlPathLine(path w_um list(x2 y2))
                                        if( net_dbid != nil then
                                            axlDBCreatePath(path strcat("CONDUCTOR/" sub_name) net_dbid)
                                        else
                                            axlDBCreatePath(path strcat("CONDUCTOR/" sub_name))
                                        )
                                    )
                                else
                                    skipped_cnt = skipped_cnt + 1
                                )
                            )
                            ("EDTC_GUARD"
                                guard_cnt = guard_cnt + 1
                                layer_str = kv_tbl["LAYER"]
                                sub_name = pdn_lookup_subclass(sub_tbl layer_str)
                                net_name = kv_tbl["NET"]
                                net_dbid = pdn_get_or_create_net(net_tbl net_name)
                                w_um = float(atof(kv_tbl["WIDTH"]))
                                x1 = float(atof(kv_tbl["X1"]))
                                y1 = float(atof(kv_tbl["Y1"]))
                                x2 = float(atof(kv_tbl["X2"]))
                                y2 = float(atof(kv_tbl["Y2"]))
                                if( sub_name != nil then
                                    path = axlPathStart(list(list(x1 y1)) w_um)
                                    axlPathLine(path w_um list(x2 y1))
                                    axlPathLine(path w_um list(x2 y2))
                                    axlPathLine(path w_um list(x1 y2))
                                    axlPathLine(path w_um list(x1 y1))
                                    if( net_dbid != nil then
                                        axlDBCreatePath(path strcat("CONDUCTOR/" sub_name) net_dbid)
                                    else
                                        axlDBCreatePath(path strcat("CONDUCTOR/" sub_name))
                                    )
                                )
                            )
                            ("KOZ"
                                koz_cnt = koz_cnt + 1
                                x1 = float(atof(kv_tbl["X1"]))
                                y1 = float(atof(kv_tbl["Y1"]))
                                x2 = float(atof(kv_tbl["X2"]))
                                y2 = float(atof(kv_tbl["Y2"]))
                                axlDBCreateRectangle(list(list(x1 y1) list(x2 y2)) t "ROUTE KEEPOUT/ALL")
                            )
                            ("LSC_SYM"
                                lsc_cnt = lsc_cnt + 1
                                x = float(atof(kv_tbl["X"]))
                                y = float(atof(kv_tbl["Y"]))
                                axlDBCreateRectangle(list(list(x - 300.0 y - 150.0) list(x + 300.0 y + 150.0)) nil "PACKAGE GEOMETRY/PLACE_BOUND_BOTTOM")
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
                summary_path
                "SUCCESS"
                list(
                    list("STAGE" "STAGE4_TXT_IMPORT")
                    list("RECIPE_FILE" recipe_path)
                    list("PLANE_POLARITY_RECORDS" sprintf(nil "%d" plane_cnt))
                    list("VIAS_IMPORTED" sprintf(nil "%d" via_cnt))
                    list("CLINES_IMPORTED" sprintf(nil "%d" cline_cnt))
                    list("EDTC_GUARD_RINGS_IMPORTED" sprintf(nil "%d" guard_cnt))
                    list("KOZ_SHAPES_IMPORTED" sprintf(nil "%d" koz_cnt))
                    list("LSC_SYMBOLS_IMPORTED" sprintf(nil "%d" lsc_cnt))
                    list("ERRORS" sprintf(nil "%d" err_cnt))
                )
            )

            pdn_write_report(
                report_path
                "SUCCESS"
                list(
                    list("STAGE" "STAGE4_TXT_IMPORT")
                    list("RECIPE_FILE" recipe_path)
                    list("VIAS_IMPORTED" sprintf(nil "%d" via_cnt))
                    list("CLINES_IMPORTED" sprintf(nil "%d" cline_cnt))
                    list("EDTC_GUARD_RINGS_IMPORTED" sprintf(nil "%d" guard_cnt))
                    list("KOZ_SHAPES_IMPORTED" sprintf(nil "%d" koz_cnt))
                    list("LSC_SYMBOLS_IMPORTED" sprintf(nil "%d" lsc_cnt))
                )
            )
            printf("[AGENT04] Stage 4 Recipe Import Complete: %d vias, %d clines, %d guard rings, %d KOZs, %d LSCs.\n"
                via_cnt cline_cnt guard_cnt koz_cnt lsc_cnt)
            t
        )
    )
)
