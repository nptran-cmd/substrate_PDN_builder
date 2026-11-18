; =============================================================================
; File: padstack_learner_batch.il
; Package: agent04_pdn_architect
; Description: Stage 1C Headless Padstack & .mcm Geometry Learner.
;              Scans conductor stackup layers, padstacks in .mcm + padpath,
;              RefDes die symbol bboxes on SURFACE/TOP, eDTC symbols on 4FCO,
;              and BGA pins on BASE/Bottom, exporting a pipe-delimited text file
;              (<cwd>/pdn_mcm_learned.txt) to avoid SKILL stack overflow.
; =============================================================================

procedure( pdn_run_padstack_learner_batch()
    let((cwd out_path report_path p d subs s idx ps_list ps ps_name is_thru start_l end_l
         cat_str syms sym sym_name sym_ref sym_layer bbo x1 y1 x2 y2
         pad_cnt sym_cnt layer_cnt bga_sub bga_pins pin pxy pnet bga_cnt)
        cwd = pdn_get_cwd()
        out_path = pdn_get_env("PDN_LEARN_OUT" strcat(cwd "/pdn_mcm_learned.txt"))
        report_path = pdn_get_env("PDN_REPORT_FILE" strcat(cwd "/pdn_report.txt"))

        d = axlDBGetDesign()
        p = outfile(out_path "w")
        layer_cnt = 0
        pad_cnt = 0
        sym_cnt = 0
        bga_cnt = 0

        if( p != nil && d != nil then
            fprintf(p "# AGENT04_MCM_LEARNED_V1\n")

            ; 1. Export Conductor Stackup Layers in Z-order
            subs = axlSubclasses("CONDUCTOR")
            idx = 0
            foreach(s subs
                idx = idx + 1
                layer_cnt = layer_cnt + 1
                fprintf(p "STACKUP_LAYER|%d|%s\n" idx s)
            )

            ; 2. Export Padstacks in Design DB
            ps_list = d->padstacks
            foreach(ps ps_list
                ps_name = ps->name
                if( ps_name != nil then
                    pad_cnt = pad_cnt + 1
                    is_thru = if( ps->isThrough then "TRUE" else "FALSE")
                    start_l = if( ps->startEnd != nil then car(ps->startEnd) else "ALL")
                    end_l = if( ps->startEnd != nil then cadr(ps->startEnd) else "ALL")
                    cat_str = "BU_UVIA"
                    if( ps->isThrough then
                        cat_str = "CORE_PTH"
                    else
                        if( rexMatchp("282" ps_name) || rexMatchp("175" ps_name) then
                            cat_str = "PP_VIA"
                        else
                            if( rexMatchp("121" ps_name) then
                                cat_str = "BU_TO_PP_VIA"
                            else
                                if( rexMatchp("560" ps_name) || rexMatchp("BGA" upperCase(ps_name)) then
                                    cat_str = "BGA_PAD"
                                else
                                    cat_str = "BU_UVIA"
                                )
                            )
                        )
                    )
                    fprintf(p "PADSTACK|%s|%s|%s|%s|%s\n" ps_name cat_str is_thru sprintf(nil "%L" start_l) sprintf(nil "%L" end_l))
                )
            )

            ; 3. Export Placed Symbols (RefDes on SURFACE/TOP, eDTC on 4FCO, LSC on BASE)
            syms = d->symbols
            foreach(sym syms
                sym_cnt = sym_cnt + 1
                sym_ref = if( sym->refdes != nil then sym->refdes else "NOREF")
                sym_name = if( sym->name != nil then sym->name else "NOSYM")
                sym_layer = if( sym->layer != nil then sym->layer else "UNKNOWN")
                bbo = sym->bBox
                if( bbo != nil then
                    x1 = float(caar(bbo))
                    y1 = float(cadar(bbo))
                    x2 = float(caadr(bbo))
                    y2 = float(cadadr(bbo))
                else
                    x1 = 0.0
                    y1 = 0.0
                    x2 = 0.0
                    y2 = 0.0
                )
                fprintf(p "SYMBOL|%s|%s|%s|%.3f|%.3f|%.3f|%.3f\n" sym_ref sym_name sym_layer x1 y1 x2 y2)
            )

            ; 4. Sample BASE / Bottom BGA Pins (up to 2500 pins for fast pocket/cluster alignment)
            bga_sub = pdn_resolve_conductor_subclass("BASE")
            if( bga_sub != nil then
                axlVisibleDesign(nil)
                axlVisibleLayer(strcat("PIN/" bga_sub) t)
                axlSetFindFilter(?enabled list("noall" "pins") ?onButtons list("noall" "pins"))
                axlClearSelSet()
                axlAddSelectAll()
                bga_pins = axlGetSelSet()
                axlClearSelSet()
                foreach(pin bga_pins
                    if( bga_cnt < 2500 then
                        bga_cnt = bga_cnt + 1
                        pxy = pin->xy
                        pnet = if( pin->net != nil && pin->net->name != nil then pin->net->name else "DUMMY")
                        fprintf(p "BGA_PIN|%s|%.3f|%.3f|%s\n" bga_sub float(car(pxy)) float(cadr(pxy)) pnet)
                    )
                )
            )

            close(p)
        )

        pdn_write_report(
            report_path
            "SUCCESS"
            list(
                list("STAGE" "STAGE1C_PADSTACK_LEARNER")
                list("LEARNED_FILE" out_path)
                list("CONDUCTOR_LAYERS" sprintf(nil "%d" layer_cnt))
                list("PADSTACKS_LEARNED" sprintf(nil "%d" pad_cnt))
                list("SYMBOLS_LEARNED" sprintf(nil "%d" sym_cnt))
                list("BGA_PINS_SAMPLED" sprintf(nil "%d" bga_cnt))
            )
        )
        printf("[AGENT04] Stage 1C Padstack & MCM Learner complete: %d layers, %d padstacks, %d symbols.\n" layer_cnt pad_cnt sym_cnt)
        t
    )
)
