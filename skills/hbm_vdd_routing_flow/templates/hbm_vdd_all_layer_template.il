; =============================================================================
; hbm_vdd_all_layer_template.il
; Reusable 4-Rail Cadence APD / Allegro SKILL All-Layer Importer Template for
; HBM4E Sites (U13..U24, Channels MEM0..MEMB):
;   VDDQ_0P85_HBM_MEM* + VDDC_1P0_HBM_MEM* + VDDQL* + VPP_1P8_HBM_MEM* + VSS
;   + Kelvin Sense Pairs (OBS_* / SNS_*) across all 27 substrate layers.
;
; Key Safeguards & Features:
;   1. O(1) SKILL `makeTable` net/padstack caches & line-by-line `gets`
;      streaming (`0` SKILL stack overflow even across all 12 HBM sites!).
;   2. Supports `SURFACE_STRIPE` filled gang-bars on `CONDUCTOR/SURFACE` (West
;      of LAVA EMIB), `PLANE` + `PLANE_VOID` (`12F/11F/10F` EMIB/Guard/CSB KOZs
;      and `4FCO..4BCO` C2257/C2258 eDTC KOZs), and `PLANE_ISLAND` 4-rail strips.
;   3. Draws `SUBSTRATE GEOMETRY/LSC_CAVITY` (`R = 500 um`, EMIB Rule #19 shadow
;      excluded) + `ROUTE KEEPOUT/BASE` (`Code D` 178 um Cu/Signal KOZ) on `BASE`.
; =============================================================================

procedure( pdnMakeRoundedRectRpathHbm( x1 y1 x2 y2 rad layerName )
  let( (r rpath)
    r = min(rad min((x2 - x1) / 2.0 (y2 - y1) / 2.0))
    if( r <= 1.0 then
      rpath = axlPathStart(list(x1:y1 x2:y1 x2:y2 x1:y2 x1:y1))
    else
      rpath = axlPathStart(list((x1 + r):y1))
      axlPathLine(rpath 0.0 (x2 - r):y1)
      axlPathArcCenter(rpath 0.0 x2:(y1 + r) nil (x2 - r):(y1 + r))
      axlPathLine(rpath 0.0 x2:(y2 - r))
      axlPathArcCenter(rpath 0.0 (x2 - r):y2 nil (x2 - r):(y2 - r))
      axlPathLine(rpath 0.0 (x1 + r):y2)
      axlPathArcCenter(rpath 0.0 x1:(y2 - r) nil (x1 + r):(y2 - r))
      axlPathLine(rpath 0.0 x1:(y1 + r))
      axlPathArcCenter(rpath 0.0 (x1 + r):y1 nil (x1 + r):(y1 + r))
    )
    rpath
  )
)

procedure( pdnRunHbmVddMasterRecipe( recipePath outMcmPath reportPath )
  let( (inPort outPort rawLine line fields recType netTbl padTbl openPlane
        countStripe countPlane countIsland countVoid countCav countLsc countVia countCline errCount
        x1 y1 x2 y2 cx cy rot rCav kozExt)

    netTbl = makeTable("hbmNetCache" nil)
    padTbl = makeTable("hbmPadCache" nil)
    openPlane = nil
    countStripe = 0
    countPlane = 0
    countIsland = 0
    countVoid = 0
    countCav = 0
    countLsc = 0
    countVia = 0
    countCline = 0
    errCount = 0

    inPort = infile(recipePath)
    unless(inPort
      error("pdnRunHbmVddMasterRecipe: Cannot open recipe file %s" recipePath)
    )

    while( gets(rawLine inPort)
      line = buildString(parseString(rawLine "\r\n") "")
      when( strlen(line) > 0 && substring(line 1 1) != "#"
        fields = parseString(line "|")
        recType = car(fields)

        when( openPlane && recType != "PLANE_VOID"
          axlDBCreateCloseShape(openPlane)
          openPlane = nil
        )

        cond(
          ( recType == "SURFACE_STRIPE"
            let( (netName lyrName netObj rpath shp)
              netName = nth(1 fields)
              lyrName = strcat("CONDUCTOR/" nth(2 fields))
              x1 = atof(nth(3 fields))
              y1 = atof(nth(4 fields))
              x2 = atof(nth(5 fields))
              y2 = atof(nth(6 fields))
              netObj = netTbl[netName]
              unless(netObj
                netObj = axlDBCreateNet(netName)
                netTbl[netName] = netObj
              )
              rpath = axlPathStart(list(x1:y1 x2:y1 x2:y2 x1:y2 x1:y1))
              shp = axlDBCreateShape(rpath t lyrName netName)
              if( shp then countStripe = countStripe + 1 else errCount = errCount + 1 )
            )
          )

          ( recType == "PLANE" || recType == "PLANE_ISLAND"
            let( (netName lyrName netObj rpath)
              netName = nth(1 fields)
              lyrName = strcat("CONDUCTOR/" nth(2 fields))
              x1 = atof(nth(3 fields))
              y1 = atof(nth(4 fields))
              x2 = atof(nth(5 fields))
              y2 = atof(nth(6 fields))
              netObj = netTbl[netName]
              unless(netObj
                netObj = axlDBCreateNet(netName)
                netTbl[netName] = netObj
              )
              rpath = axlPathStart(list(x1:y1 x2:y1 x2:y2 x1:y2 x1:y1))
              openPlane = axlDBCreateOpenShape(rpath t lyrName netName)
              if( openPlane then
                if( recType == "PLANE" then
                  countPlane = countPlane + 1
                else
                  countIsland = countIsland + 1
                )
              else
                errCount = errCount + 1
              )
            )
          )

          ( recType == "PLANE_VOID"
            when( openPlane
              let( (vpath)
                x1 = atof(nth(2 fields))
                y1 = atof(nth(3 fields))
                x2 = atof(nth(4 fields))
                y2 = atof(nth(5 fields))
                vpath = axlPathStart(list(x1:y1 x2:y1 x2:y2 x1:y2 x1:y1))
                if( axlDBCreateVoid(openPlane vpath) then
                  countVoid = countVoid + 1
                else
                  errCount = errCount + 1
                )
              )
            )
          )

          ( recType == "CAVITY_OUTLINE"
            let( (cavPath kozPath)
              x1 = atof(nth(2 fields))
              y1 = atof(nth(3 fields))
              x2 = atof(nth(4 fields))
              y2 = atof(nth(5 fields))
              rCav = atof(nth(6 fields))
              kozExt = atof(nth(7 fields))
              unless( axlIsLayer("SUBSTRATE GEOMETRY/LSC_CAVITY")
                axlLayerCreateNonConductor("SUBSTRATE GEOMETRY/LSC_CAVITY")
              )
              cavPath = pdnMakeRoundedRectRpathHbm(x1 y1 x2 y2 rCav "SUBSTRATE GEOMETRY/LSC_CAVITY")
              axlDBCreateShape(cavPath nil "SUBSTRATE GEOMETRY/LSC_CAVITY")
              when( kozExt > 0.0 && axlIsLayer("ROUTE KEEPOUT/BASE")
                kozPath = pdnMakeRoundedRectRpathHbm((x1 - kozExt) (y1 - kozExt) (x2 + kozExt) (y2 + kozExt) (rCav + kozExt) "ROUTE KEEPOUT/BASE")
                axlDBCreateShape(kozPath t "ROUTE KEEPOUT/BASE")
              )
              countCav = countCav + 1
            )
          )

          ( recType == "LSC_SYM"
            let( (refDes symName mirFlag p1Net p2Net symRes symObj pinList p1 p2)
              axlSetVariable("logic_edit_enabled" t)
              refDes = nth(1 fields)
              symName = nth(2 fields)
              cx = atof(nth(3 fields))
              cy = atof(nth(4 fields))
              rot = atof(nth(5 fields))
              mirFlag = (nth(6 fields) == "MIRROR_YES")
              p1Net = nth(7 fields)
              p2Net = nth(8 fields)
              unless( netTbl[p1Net] netTbl[p1Net] = or(axlDBFindByName('net p1Net) axlDBCreateNet(p1Net)) )
              unless( netTbl[p2Net] netTbl[p2Net] = or(axlDBFindByName('net p2Net) axlDBCreateNet(p2Net)) )
              let( (cwd dp devName devFile dfp)
                cwd = or(axlGetVariable("cwd") ".")
                devName = strcat("LSC_DEV_" symName)
                devFile = strcat(cwd "/" devName ".txt")
                unless( isFile(devFile)
                  dfp = outfile(devFile "w")
                  when( dfp
                    fprintf(dfp "(DEVICE FILE: %s)\nPACKAGE %s\nCLASS DISCRETE\nPINCOUNT 2\nEND\n" devName symName)
                    close(dfp)
                  )
                )
                dp = or(axlGetVariable("devpath") ".")
                unless( rexMatchp(cwd dp) axlSetVariable("devpath" strcat(cwd " " dp)) )
                errset(axlDBCreateComponent(refDes devName symName "DISCRETE") nil)
              )
              symRes = errset(axlDBCreateSymbol(refDes cx:cy nil rot) nil)
              symObj = if( symRes && car(symRes) then
                         if( listp(car(symRes)) then car(car(symRes)) else car(symRes) )
                       else nil )
              when( symObj && symObj->pins
                let( (se0)
                  se0 = if( car(symObj->pins)->startEnd then upperCase(sprintf(nil "%L" car(symObj->pins)->startEnd)) else "" )
                  unless( rexMatchp("BASE" se0) || rexMatchp("BOTTOM" se0)
                    errset(axlDeleteObject(symObj) nil)
                    symRes = errset(axlDBCreateSymbol(refDes cx:cy t rot) nil)
                    symObj = if( symRes && car(symRes) then
                               if( listp(car(symRes)) then car(car(symRes)) else car(symRes) )
                             else nil )
                  )
                )
              )
              if( symObj then
                countLsc = countLsc + 1
                pinList = symObj->pins
                when( pinList && length(pinList) >= 2
                  p1 = nth(0 pinList)
                  p2 = nth(1 pinList)
                  foreach( pObj pinList
                    when( pObj->number == "1" p1 = pObj )
                    when( pObj->number == "2" p2 = pObj )
                  )
                  errset(axlChangeNet(p1 p1Net) nil)
                  errset(axlChangeNet(p2 p2Net) nil)
                )
              else
                errCount = errCount + 1
              )
            )
          )

          ( recType == "VIA"
            let( (netName padName padObj viaRes)
              netName = nth(1 fields)
              padName = nth(2 fields)
              cx = atof(nth(5 fields))
              cy = atof(nth(6 fields))
              unless( netTbl[netName]
                netTbl[netName] = axlDBCreateNet(netName)
              )
              padObj = padTbl[padName]
              unless( padObj
                padObj = axlLoadPadstack(padName)
                padTbl[padName] = padObj
              )
              viaRes = axlDBCreateVia(padName cx:cy netName nil 0.0 nil)
              if( viaRes then countVia = countVia + 1 else errCount = errCount + 1 )
            )
          )

          ( recType == "CLINE"
            let( (netName lyrName wUm lineRes)
              netName = nth(1 fields)
              lyrName = strcat("CONDUCTOR/" nth(2 fields))
              wUm = atof(nth(3 fields))
              x1 = atof(nth(4 fields))
              y1 = atof(nth(5 fields))
              x2 = atof(nth(6 fields))
              y2 = atof(nth(7 fields))
              unless( netTbl[netName]
                netTbl[netName] = axlDBCreateNet(netName)
              )
              lineRes = axlDBCreateLine(list(x1:y1 x2:y2) wUm lyrName netName)
              if( lineRes then countCline = countCline + 1 else errCount = errCount + 1 )
            )
          )
        )
      )
    )

    when( openPlane
      axlDBCreateCloseShape(openPlane)
      openPlane = nil
    )
    close(inPort)
    axlDBRefreshId(nil)

    when( outMcmPath && strlen(outMcmPath) > 0
      axlSaveDesign(?design outMcmPath ?noConfirm t)
    )

    when( reportPath && strlen(reportPath) > 0
      outPort = outfile(reportPath "w")
      when( outPort
        fprintf(outPort "HBM_VDD_ALL_LAYER_IMPORT_SUMMARY\n")
        fprintf(outPort "SURFACE_STRIPES=%d\nPLANES=%d\nISLANDS=%d\nVOIDS=%d\nCAVITIES=%d\nLSCS=%d\nVIAS=%d\nCLINES=%d\nERRORS=%d\n"
          countStripe countPlane countIsland countVoid countCav countLsc countVia countCline errCount)
        close(outPort)
      )
    )
    t
  )
)
