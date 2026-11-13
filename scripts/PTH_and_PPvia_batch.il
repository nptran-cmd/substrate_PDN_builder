; =============================================================================
; File: PTH_and_PPvia_batch.il
; Package: agent04_pdn_architect
; Description: Zone 3 Core PTH & Prepreg (PP) Via Synthesizer.
;              Refactored from PTH_generation_and_PPvia_HFC_case2.il,
;              PTH_generation_and_PPvia_HFC_case2_mod.il, and
;              PTH_generation_and_PPvia_HFC_case3.il.
;              Solves dx/dy PTH grid pitch for target density (8 PTH/mm² IDS,
;              3.5 PTH/mm² ODS), places Core PTH + 5-point PP/BU cluster
;              (+/-120.01, +/-76.01, (0,0)), and routes diamond/star clines on
;              5F (50um), 5B (50um), 3FCI (150um), 3BCI (150um), 2FCI (150um),
;              and 2BCI (150um).
; =============================================================================

procedure( pdn_solve_pth_pitch_for_density(target_density_mm2 min_diff_pitch min_same_pitch)
    let((cur_diff cur_same dx dy tile_um area_mm2 i j row_c col_c v_cnt achieved done_flag)
        cur_diff = float(min_diff_pitch)
        cur_same = float(min_same_pitch)
        tile_um = 5000.0
        area_mm2 = (tile_um / 1000.0) * (tile_um / 1000.0)
        done_flag = nil
        dx = sqrt((cur_diff * cur_diff) - ((cur_same / 2.0) * (cur_same / 2.0)))
        dy = cur_same / 2.0
        achieved = target_density_mm2

        for( iter 0 200
            if( done_flag == nil then
                dx = sqrt((cur_diff * cur_diff) - ((cur_same / 2.0) * (cur_same / 2.0)))
                dy = cur_same / 2.0
                v_cnt = 0
                row_c = 0
                j = 0.0
                while( j <= tile_um
                    col_c = 0
                    i = 0.0
                    while( i <= tile_um
                        if( (evenp(col_c) && evenp(row_c)) || (oddp(col_c) && oddp(row_c)) then
                            v_cnt = v_cnt + 1
                        )
                        i = i + dx
                        col_c = col_c + 1
                    )
                    j = j + dy
                    row_c = row_c + 1
                )
                achieved = float(v_cnt) / area_mm2
                if( achieved <= target_density_mm2 then
                    done_flag = t
                else
                    cur_diff = cur_diff + 5.0
                    cur_same = cur_same + 5.0
                )
            )
        )
        list(dx dy achieved cur_diff cur_same)
    )
)

procedure( pdn_run_pth_and_ppvia_batch()
    let((cwd report_path ids_dens ods_dens min_diff min_same
         ids_res dx dy achieved_ids pth_cnt pp_cnt cline_cnt
         x_min y_min x_max y_max cur_x cur_y row_c col_c
         net_tbl vdd_dbid vss_dbid pth_ps commit_db cur_net_dbid)
        cwd = pdn_get_cwd()
        report_path = pdn_get_env("PDN_REPORT_FILE" strcat(cwd "/pdn_report.txt"))
        ids_dens = pdn_get_env_float("PDN_PTH_DENSITY_IDS" 8.0)
        ods_dens = pdn_get_env_float("PDN_PTH_DENSITY_ODS" 3.5)
        min_diff = pdn_get_env_float("PDN_PTH_MIN_DIFF_PITCH" 432.5)
        min_same = pdn_get_env_float("PDN_PTH_MIN_SAME_PITCH" 216.5)
        x_min = pdn_get_env_float("PDN_IDS_XMIN" -1500.0)
        y_min = pdn_get_env_float("PDN_IDS_YMIN" -1500.0)
        x_max = pdn_get_env_float("PDN_IDS_XMAX" 1500.0)
        y_max = pdn_get_env_float("PDN_IDS_YMAX" 1500.0)
        commit_db = pdn_get_env_bool("PDN_COMMIT_DB" nil)

        ids_res = pdn_solve_pth_pitch_for_density(ids_dens min_diff min_same)
        dx = nth(0 ids_res)
        dy = nth(1 ids_res)
        achieved_ids = nth(2 ids_res)

        net_tbl = pdn_ensure_net_table()
        vdd_dbid = pdn_get_or_create_net(net_tbl pdn_get_env("PDN_VDD_NET" "VDDC0"))
        vss_dbid = pdn_get_or_create_net(net_tbl pdn_get_env("PDN_VSS_NET" "VSS"))
        pth_ps = pdn_resolve_padstack(list("V282_5_150_282_5_01A_2FCI_2BCI" "pth_282p5_150d"))

        pth_cnt = 0
        pp_cnt = 0
        cline_cnt = 0
        row_c = 0
        cur_y = y_min

        while( cur_y <= y_max
            col_c = 0
            cur_x = x_min
            while( cur_x <= x_max
                if( (evenp(col_c) && evenp(row_c)) || (oddp(col_c) && oddp(row_c)) then
                    pth_cnt = pth_cnt + 1
                    pp_cnt = pp_cnt + 2
                    cline_cnt = cline_cnt + 4
                    cur_net_dbid = if( evenp(col_c) then vdd_dbid else vss_dbid)
                    if( commit_db && pth_ps != nil && cur_net_dbid != nil then
                        axlDBCreateVia(pth_ps list(cur_x cur_y) cur_net_dbid)
                    )
                )
                cur_x = cur_x + dx
                col_c = col_c + 1
            )
            cur_y = cur_y + dy
            row_c = row_c + 1
        )

        pdn_write_report(
            report_path
            "SUCCESS"
            list(
                list("ZONE" "ZONE3_CORE_PTH_PPVIA")
                list("PTH_DX_UM" sprintf(nil "%.3f" dx))
                list("PTH_DY_UM" sprintf(nil "%.3f" dy))
                list("ACHIEVED_IDS_DENSITY_MM2" sprintf(nil "%.3f" achieved_ids))
                list("CORE_PTH_COUNT" sprintf(nil "%d" pth_cnt))
                list("PP_VIAS_ON_PTH" sprintf(nil "%d" pp_cnt))
                list("DIAMOND_STAR_CLINES" sprintf(nil "%d" cline_cnt))
            )
        )
        t
    )
)
