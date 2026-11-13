; =============================================================================
; File: pdn_Pipeline_batch.il
; Package: agent04_pdn_architect
; Description: Master headless SKILL dispatcher for Agent 04 (PDN Architect).
;              Can be invoked via pdnDispatchBatchJob("STAGE4_IMPORT_RECIPE")
;              from an Allegro .scr script created by CadenceBatchRunner.
; =============================================================================

procedure( pdnDispatchBatchJob(action @optional save_str)
    let((act)
        act = upperCase(action)
        axlSetVariable("PDN_ACTION" act)
        if( save_str != nil && save_str != "" then
            axlSetVariable("PDN_SAVE_DESIGN" save_str)
        )

        printf("[AGENT04] Dispatching pdnDispatchBatchJob action = %s in cwd = %s\n" act pdn_get_cwd())
        case( act
            ("STAGE1_FULL_EXTRACT"
                pdn_run_stage1_full_extractor()
            )
            ("SURFACE_BUMP_ROUTE"
                pdn_import_surface_recipe_batch()
            )
            ("PTH_4FCO_4BCO_ROUTE"
                pdn_import_pth_4fco_4bco_recipe_batch()
            )
            ("BASE_LSC_BGA_ROUTE"
                pdn_import_base_lsc_bga_recipe_batch()
            )
            ("FULL_27LAYER_APD_IMPLEMENT"
                pdnRunFull27LayerArchitectAndImplement()
            )
            ("PADSTACK_LEARN"
                pdn_run_padstack_learner_batch()
            )
            ("ZONE1_ABOVE_BU"
                pdn_run_above_bu_batch()
            )
            ("ZONE2_EDTC_GUARD"
                pdn_run_edtc_guard_batch()
            )
            ("ZONE3_CORE_PTH"
                pdn_run_pth_and_ppvia_batch()
            )
            ("ZONE4_BELOW_BU"
                pdn_run_below_bu_batch()
            )
            ("ZONE5_BASE_LSC"
                pdn_run_lsc_pocket_placer_batch()
            )
            ("STAGE4_IMPORT_RECIPE"
                pdn_run_import_from_txt_batch()
            )
            (t
                pdn_run_import_from_txt_batch()
            )
        )
    )
)
