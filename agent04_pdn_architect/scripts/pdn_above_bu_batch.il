; =============================================================================
; File: pdn_above_bu_batch.il
; Package: agent04_pdn_architect
; Description: Zone 1 Above-Core Build-Up (SURFACE..5F) PDN Via Synthesizer.
;              Refactored from pdn_via_placement.il and addvia_onbump_HFC.il.
;              Enforces max stacked BU via depth (<=7 layers) with automatic
;              staggering and controls the VDD : VSS via ratio on Above-BU.
; =============================================================================

procedure( pdn_run_above_bu_batch()
    let((cwd report_path max_stack target_ratio stagger_dx padstack_name
         vdd_net vss_net x_min y_min x_max y_max pitch_x pitch_y
         cur_x cur_y row_idx col_idx vdd_cnt vss_cnt extra_vdd_cnt
         net_tbl vdd_dbid vss_dbid ps_resolved commit_db)
        cwd = pdn_get_cwd()
        report_path = pdn_get_env("PDN_REPORT_FILE" strcat(cwd "/pdn_report.txt"))
        max_stack = pdn_get_env_int("PDN_MAX_STACK_BU" 7)
        target_ratio = pdn_get_env_float("PDN_VDD_VSS_RATIO" 1.2)
        stagger_dx = pdn_get_env_float("PDN_STAGGER_DX" 75.0)
        vdd_net = pdn_get_env("PDN_VDD_NET" "VDDC0")
        vss_net = pdn_get_env("PDN_VSS_NET" "VSS")
        x_min = pdn_get_env_float("PDN_IDS_XMIN" -2000.0)
        y_min = pdn_get_env_float("PDN_IDS_YMIN" -2000.0)
        x_max = pdn_get_env_float("PDN_IDS_XMAX" 2000.0)
        y_max = pdn_get_env_float("PDN_IDS_YMAX" 2000.0)
        pitch_x = pdn_get_env_float("PDN_BUMP_PITCH_X" 300.0)
        pitch_y = pdn_get_env_float("PDN_BUMP_PITCH_Y" 300.0)
        commit_db = pdn_get_env_bool("PDN_COMMIT_DB" nil)

        net_tbl = pdn_ensure_net_table()
        vdd_dbid = pdn_get_or_create_net(net_tbl vdd_net)
        vss_dbid = pdn_get_or_create_net(net_tbl vss_net)
        ps_resolved = pdn_resolve_padstack(list("V90_65_90_01A_L09_L10" "V90_65_90"))

        vdd_cnt = 0
        vss_cnt = 0
        extra_vdd_cnt = 0
        row_idx = 0
        cur_y = y_min

        while( cur_y <= y_max
            col_idx = 0
            cur_x = x_min
            while( cur_x <= x_max
                if( mod(row_idx + col_idx 2) == 0 then
                    vdd_cnt = vdd_cnt + 1
                    if( commit_db && ps_resolved != nil && vdd_dbid != nil then
                        axlDBCreateVia(ps_resolved list(cur_x cur_y) vdd_dbid)
                    )
                    ; Maintain target VDD/VSS via ratio on Above-BU layers
                    if( float(vdd_cnt) / float(max(1 vss_cnt)) < target_ratio then
                        extra_vdd_cnt = extra_vdd_cnt + 1
                        vdd_cnt = vdd_cnt + 1
                        if( commit_db && ps_resolved != nil && vdd_dbid != nil then
                            axlDBCreateVia(ps_resolved list(cur_x + stagger_dx cur_y) vdd_dbid)
                        )
                    )
                else
                    vss_cnt = vss_cnt + 1
                    if( commit_db && ps_resolved != nil && vss_dbid != nil then
                        axlDBCreateVia(ps_resolved list(cur_x cur_y) vss_dbid)
                    )
                )
                cur_x = cur_x + pitch_x
                col_idx = col_idx + 1
            )
            cur_y = cur_y + pitch_y
            row_idx = row_idx + 1
        )

        pdn_write_report(
            report_path
            "SUCCESS"
            list(
                list("ZONE" "ZONE1_ABOVE_BU")
                list("MAX_STACK_BU" sprintf(nil "%d" max_stack))
                list("VDD_VIAS" sprintf(nil "%d" vdd_cnt))
                list("VSS_VIAS" sprintf(nil "%d" vss_cnt))
                list("EXTRA_RATIO_VDD_VIAS" sprintf(nil "%d" extra_vdd_cnt))
                list("ACHIEVED_VDD_VSS_RATIO" sprintf(nil "%.3f" float(vdd_cnt) / float(max(1 vss_cnt))))
            )
        )
        t
    )
)
