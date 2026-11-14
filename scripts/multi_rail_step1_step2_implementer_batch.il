; =============================================================================
; File: multi_rail_step1_step2_implementer_batch.il
; Package: agent04_pdn_architect
; Description:
;   Headless Cadence APD 25.1 Multi-Rail Polygon, Dynamic Plane / Static Guard Band,
;   `SUBSTRATE GEOMETRY/recess_cavity_pdn` LSC Recess KOZ, EMIB/CSB, HBM Gang-Bar &
;   27-Layer Batch Implementer + Post-Route Connectivity Verifier.
; =============================================================================

procedure( pdnMrGetOrMakeNet( netTbl netName )
  let( (dbNet)
    if( !netName || netName == "" || netName == "__ISOLATED__" then
      nil
    else
      dbNet = netTbl[netName]
      unless( dbNet
        dbNet = axlDBFindByName('net netName)
        unless( dbNet
          dbNet = axlDBCreateNet(netName)
        )
        when( dbNet
          netTbl[netName] = dbNet
        )
      )
      dbNet
    )
  )
)

procedure( pdnMrGetPadstack( padTbl padName )
  let( (psObj resolved fbName)
    resolved = padTbl[padName]
    unless( resolved
      psObj = or(axlDBFindByName('padstack padName) axlLoadPadstack(padName))
      if( psObj then
        resolved = padName
        padTbl[padName] = resolved
      else
        fbName = cond(
          ( rexMatchp("10B_11B" upperCase(padName)) "V77_49_77_10B_11B_01A" )
          ( rexMatchp("11B_12B" upperCase(padName)) "V77_49_77_11B_12B_01A" )
          ( t nil )
        )
        when( fbName
          psObj = or(axlDBFindByName('padstack fbName) axlLoadPadstack(fbName))
          when( psObj
            resolved = fbName
            padTbl[padName] = resolved
          )
        )
      )
    )
    resolved
  )
)

procedure( pdnMrParseVertices( vertStr )
  let( (pairs p xy x y pts firstPt)
    pts = nil
    firstPt = nil
    pairs = parseString(vertStr ";")
    foreach( p pairs
      xy = parseString(p ",")
      when( length(xy) >= 2
        x = float(atof(nth(0 xy)))
        y = float(atof(nth(1 xy)))
        unless( firstPt firstPt = list(x y) )
        pts = append1(pts list(x y))
      )
    )
    when( firstPt && length(pts) >= 3
      pts = append1(pts firstPt)
    )
    pts
  )
)

procedure( pdnMrRoundedRectPath( x1 y1 x2 y2 rad @optional (lineW 0.0) )
  let( (r rpath)
    r = min(float(rad) min((x2 - x1) / 2.0 (y2 - y1) / 2.0))
    if( r <= 1.0 then
      rpath = axlPathStart(list(x1:y1 x2:y1 x2:y2 x1:y2 x1:y1) lineW)
    else
      rpath = axlPathStart(list((x1 + r):y1) lineW)
      axlPathLine(rpath lineW (x2 - r):y1)
      axlPathArcCenter(rpath lineW x2:(y1 + r) nil (x2 - r):(y1 + r))
      axlPathLine(rpath lineW x2:(y2 - r))
      axlPathArcCenter(rpath lineW (x2 - r):y2 nil (x2 - r):(y2 - r))
      axlPathLine(rpath lineW (x1 + r):y2)
      axlPathArcCenter(rpath lineW x1:(y2 - r) nil (x1 + r):(y2 - r))
      axlPathLine(rpath lineW x1:(y1 + r))
      axlPathArcCenter(rpath lineW (x1 + r):y1 nil (x1 + r):(y1 + r))
    )
    rpath
  )
)

procedure( pdnMrCreateHollowRingShape( ox1 oy1 ox2 oy2 orad ix1 iy1 ix2 iy2 irad targetLayer )
  let( (oPath iPath oShp cRes)
    oPath = pdnMrRoundedRectPath(ox1 oy1 ox2 oy2 orad 0.0)
    iPath = pdnMrRoundedRectPath(ix1 iy1 ix2 iy2 irad 0.0)
    oShp = car(errset(axlDBCreateOpenShape(oPath t targetLayer nil) nil))
    when( oShp
      errset(axlDBCreateVoid(oShp iPath) nil)
      cRes = car(errset(axlDBCreateCloseShape(oShp) nil))
    )
    cRes
  )
)

procedure( pdnMrCreatePolyRingShape( outerPts innerPts targetLayer )
  let( (oPath iPath oShp cRes)
    when( outerPts && length(outerPts) >= 4
      oPath = axlPathStart(outerPts 0.0)
      oShp = car(errset(axlDBCreateOpenShape(oPath t targetLayer nil) nil))
      when( oShp
        when( innerPts && length(innerPts) >= 4
          iPath = axlPathStart(innerPts 0.0)
          errset(axlDBCreateVoid(oShp iPath) nil)
        )
        cRes = car(errset(axlDBCreateCloseShape(oShp) nil))
      )
    )
    cRes
  )
)

procedure( pdnMrEnsureLscDev( symName )
  let( (devName devFile outP)
    devName = strcat("LSC_DEV_" symName)
    devFile = strcat(devName ".txt")
    unless( isFile(devFile)
      outP = outfile(devFile "w")
      when( outP
        fprintf(outP "(DEVICE FILE: %s)\nPACKAGE %s\nCLASS DISCRETE\nPINCOUNT 2\nEND\n" devName symName)
        close(outP)
      )
    )
    devName
  )
)

procedure( pdnMrPinIsOnBase( pObj )
  let( (seStr)
    seStr = if( pObj && pObj->startEnd then upperCase(sprintf(nil "%L" pObj->startEnd)) else "" )
    ((rexMatchp("BASE" seStr) || rexMatchp("BOTTOM" seStr)) && !rexMatchp("SURFACE" seStr))
  )
)

procedure( pdnMrPlaceBaseLsc( refDes symName cx cy rotDeg p1Net p2Net netTbl )
  let( (devType compObj plcRes placedSym p1Obj p2Obj pNum)
    devType = pdnMrEnsureLscDev(symName)
    compObj = axlDBFindByName('component refDes)
    when( compObj && compObj->symbol
      errset(axlDeleteObject(compObj->symbol) nil)
    )
    unless( compObj
      errset(axlDBCreateComponent(refDes devType) nil)
      unless( axlDBFindByName('component refDes)
        errset(axlDBCreateComponent(refDes devType symName "DISCRETE") nil)
      )
    )
    placedSym = nil
    ; Mandatory rule: try mir=nil first and verify pin->startEnd lands on CONDUCTOR/BASE!
    plcRes = errset(axlDBCreateSymbol(refDes list(float(cx) float(cy)) nil float(rotDeg)) nil)
    when( plcRes && car(plcRes)
      placedSym = if( listp(car(plcRes)) then car(car(plcRes)) else car(plcRes) )
    )
    when( placedSym && placedSym->pins && !pdnMrPinIsOnBase(car(placedSym->pins))
      errset(axlDeleteObject(placedSym) nil)
      placedSym = nil
      plcRes = errset(axlDBCreateSymbol(refDes list(float(cx) float(cy)) t float(rotDeg)) nil)
      when( plcRes && car(plcRes)
        placedSym = if( listp(car(plcRes)) then car(car(plcRes)) else car(plcRes) )
      )
    )
    when( placedSym && placedSym->pins && length(placedSym->pins) >= 2
      pdnMrGetOrMakeNet(netTbl p1Net)
      pdnMrGetOrMakeNet(netTbl p2Net)
      p1Obj = nil
      p2Obj = nil
      foreach( p placedSym->pins
        pNum = if( p->number then sprintf(nil "%s" p->number) else "" )
        if( pNum == "1" then p1Obj = p else when( pNum == "2" p2Obj = p ) )
      )
      unless( p1Obj p1Obj = nth(0 placedSym->pins) )
      unless( p2Obj p2Obj = nth(1 placedSym->pins) )
      when( p1Obj errset(axlChangeNet(p1Obj p1Net) nil) )
      when( p2Obj errset(axlChangeNet(p2Obj p2Net) nil) )
    )
    placedSym
  )
)

procedure( pdnMrEnsureLibPaths()
  let( (libDir psmList padList devList)
    libDir = "G:/My Drive/HFC_TO_docs/Library"
    when( isDir(libDir)
      psmList = axlGetVariableList("psmpath")
      unless( member(libDir psmList) axlSetVariable("psmpath" cons(libDir psmList)) )
      padList = axlGetVariableList("padpath")
      unless( member(libDir padList) axlSetVariable("padpath" cons(libDir padList)) )
    )
    devList = axlGetVariableList("devpath")
    unless( member("." devList) axlSetVariable("devpath" cons("." devList)) )
  )
)

procedure( pdnImplementMultiRailStep1Step2Batch( recipePath saveDesign outMcmPath reportPath )
  let( (inPort rawLine line parts rType netTbl padTbl curStaticOpen curDynBndry
        polyCnt dynCnt staticGuardCnt voidCnt cavCnt recessKozCnt viaCnt clineCnt errCnt
        subStr netStr shapeMode hasVoids vertField pts rPath lyrSub netId shpRes shpObj
        cx1 cy1 cx2 cy2 rCav kozExt safeIn cPath kPath recessLayer
        padName xVal yVal wVal x1Val y1Val x2Val y2Val d outP checkNets)

    errset(axlDBControl('drcEnable nil) nil)
    errset(axlDBControl('dynamicFillMode 'disabled) nil)
    axlSetVariable("logic_edit_enabled" t)
    pdnMrEnsureLibPaths()

    ; Ensure non-conductor inspection layers exist (including `SUBSTRATE GEOMETRY/recess_cavity_pdn`!)
    recessLayer = "SUBSTRATE GEOMETRY/recess_cavity_pdn"
    unless( axlIsLayer(recessLayer)
      axlLayerCreateNonConductor(recessLayer)
    )
    unless( axlIsLayer("SUBSTRATE GEOMETRY/LSC_CAVITY")
      axlLayerCreateNonConductor("SUBSTRATE GEOMETRY/LSC_CAVITY")
    )

    netTbl = makeTable("pdnMrNetTbl" nil)
    padTbl = makeTable("pdnMrPadTbl" nil)
    curStaticOpen = nil
    curDynBndry   = nil

    polyCnt        = 0
    dynCnt         = 0
    staticGuardCnt = 0
    voidCnt        = 0
    cavCnt         = 0
    recessKozCnt   = 0
    viaCnt         = 0
    clineCnt       = 0
    errCnt         = 0

    inPort = infile(recipePath)
    when( inPort
      while( gets(rawLine inPort)
        line = buildString(parseString(rawLine "\r\n") "")
        when( strlen(line) > 0 && substring(line 1 1) != "#"
          parts = parseString(line "|")
          when( length(parts) >= 1
            rType = upperCase(nth(0 parts))
            cond(
              ; POLY_SHAPE|<layer>|<net>|<DYNAMIC|STATIC_GUARD>|<YES|NO>|<verts>
              ; (also supports legacy 5-field POLY_SHAPE|<layer>|<net>|<YES|NO>|<verts>)
              ( rType == "POLY_SHAPE" && length(parts) >= 5
                when( curStaticOpen
                  errset(axlDBCreateCloseShape(curStaticOpen) nil)
                  curStaticOpen = nil
                )
                curDynBndry = nil

                subStr = upperCase(nth(1 parts))
                if( subStr == "TOP" then subStr = "SURFACE" )
                if( subStr == "BOTTOM" then subStr = "BASE" )
                netStr = nth(2 parts)

                if( length(parts) >= 6 then
                  shapeMode = upperCase(nth(3 parts))
                  hasVoids  = upperCase(nth(4 parts))
                  vertField = nth(5 parts)
                else
                  shapeMode = if( netStr == "__ISOLATED__" then "STATIC_GUARD" else "DYNAMIC" )
                  hasVoids  = upperCase(nth(3 parts))
                  vertField = nth(4 parts)
                )

                pts = pdnMrParseVertices(vertField)
                when( length(pts) >= 4
                  lyrSub = strcat("CONDUCTOR/" subStr)
                  netId  = pdnMrGetOrMakeNet(netTbl netStr)
                  rPath  = axlPathStart(pts)

                  if( shapeMode == "STATIC_GUARD" || netStr == "__ISOLATED__" then
                    ; STATIC SOLID COPPER SHAPE (Guard Rings on 10F & eDTC Guard Bands on 4FCO/4BCO)
                    if( hasVoids == "YES" then
                      curStaticOpen = car(errset(axlDBCreateOpenShape(rPath t lyrSub nil) nil))
                      if( curStaticOpen then
                        polyCnt = polyCnt + 1
                        staticGuardCnt = staticGuardCnt + 1
                      else
                        errCnt = errCnt + 1
                      )
                    else
                      if( car(errset(axlDBCreateShape(rPath t lyrSub nil) nil)) then
                        polyCnt = polyCnt + 1
                        staticGuardCnt = staticGuardCnt + 1
                      else
                        errCnt = errCnt + 1
                      )
                    )
                  else
                    ; TRUE DYNAMIC COPPER SHAPE (`axlShapeChangeDynamicType` -> `shapeBoundary != nil`)!
                    shpRes = car(errset(axlDBCreateShape(rPath t lyrSub netId) nil))
                    shpObj = if( listp(shpRes) car(shpRes) shpRes )
                    if( shpObj then
                      curDynBndry = car(errset(axlShapeChangeDynamicType(shpObj t t) nil))
                      if( curDynBndry then
                        polyCnt = polyCnt + 1
                        dynCnt  = dynCnt + 1
                      else
                        errCnt = errCnt + 1
                      )
                    else
                      errCnt = errCnt + 1
                    )
                  )
                )
              )

              ( rType == "POLY_VOID" && length(parts) >= 2
                pts = pdnMrParseVertices(nth(1 parts))
                when( length(pts) >= 4
                  rPath = axlPathStart(pts)
                  cond(
                    ( curDynBndry
                      if( car(errset(axlDBCreateVoid(curDynBndry rPath) nil)) then
                        voidCnt = voidCnt + 1
                      else
                        errCnt = errCnt + 1
                      )
                    )
                    ( curStaticOpen
                      if( car(errset(axlDBCreateVoid(curStaticOpen rPath) nil)) then
                        voidCnt = voidCnt + 1
                      else
                        errCnt = errCnt + 1
                      )
                    )
                  )
                )
              )

              ( rType == "POLY_CLOSE"
                when( curStaticOpen
                  errset(axlDBCreateCloseShape(curStaticOpen) nil)
                  curStaticOpen = nil
                )
                curDynBndry = nil
              )

              ; CAVITY|<id>|<cx1>|<cy1>|<cx2>|<cy2>|<rCav>|<kozExt>|[lscSafeIn]
              ( rType == "CAVITY" && length(parts) >= 8
                cx1    = float(atof(nth(2 parts)))
                cy1    = float(atof(nth(3 parts)))
                cx2    = float(atof(nth(4 parts)))
                cy2    = float(atof(nth(5 parts)))
                rCav   = float(atof(nth(6 parts)))
                kozExt = float(atof(nth(7 parts)))
                safeIn = if( length(parts) >= 9 then float(atof(nth(8 parts))) else 225.0 )

                ; 1. Mechanical Recess Cavity contour on `SUBSTRATE GEOMETRY/LSC_CAVITY`
                cPath = pdnMrRoundedRectPath(cx1 cy1 cx2 cy2 rCav 0.0)
                axlDBCreateShape(cPath t "SUBSTRATE GEOMETRY/LSC_CAVITY")

                ; 2. Designer Recess KOZ verification geometry on `SUBSTRATE GEOMETRY/recess_cavity_pdn`:
                ;    (a) Outer +178 um BASE Cu/BGA Recess KOZ ring + 25 um outline
                when( kozExt > 0.0
                  pdnMrCreateHollowRingShape(
                    (cx1 - kozExt) (cy1 - kozExt) (cx2 + kozExt) (cy2 + kozExt) (rCav + kozExt)
                    cx1 cy1 cx2 cy2 rCav
                    recessLayer
                  )
                  kPath = pdnMrRoundedRectPath((cx1 - kozExt) (cy1 - kozExt) (cx2 + kozExt) (cy2 + kozExt) (rCav + kozExt) 25.0)
                  axlDBCreatePath(kPath recessLayer)
                  recessKozCnt = recessKozCnt + 2
                  when( axlIsLayer("ROUTE KEEPOUT/BASE")
                    axlDBCreateShape(
                      pdnMrRoundedRectPath((cx1 - kozExt) (cy1 - kozExt) (cx2 + kozExt) (cy2 + kozExt) (rCav + kozExt) 0.0)
                      t "ROUTE KEEPOUT/BASE"
                    )
                  )
                )

                ;    (b) Inner 225 um LSC-SRO-to-Cavity wall/corner Recess KOZ ring + 20 um safe-envelope outline
                when( safeIn > 0.0 && (cx2 - cx1) > (2.0 * safeIn + 100.0) && (cy2 - cy1) > (2.0 * safeIn + 100.0)
                  pdnMrCreateHollowRingShape(
                    cx1 cy1 cx2 cy2 rCav
                    (cx1 + safeIn) (cy1 + safeIn) (cx2 - safeIn) (cy2 - safeIn) max(25.0 (rCav - safeIn))
                    recessLayer
                  )
                  axlDBCreatePath(
                    pdnMrRoundedRectPath((cx1 + safeIn) (cy1 + safeIn) (cx2 - safeIn) (cy2 - safeIn) max(25.0 (rCav - safeIn)) 20.0)
                    recessLayer
                  )
                  recessKozCnt = recessKozCnt + 2
                )

                ;    (c) 25 um Cavity Wall reference path directly on `SUBSTRATE GEOMETRY/recess_cavity_pdn`
                axlDBCreatePath(pdnMrRoundedRectPath(cx1 cy1 cx2 cy2 rCav 25.0) recessLayer)
                recessKozCnt = recessKozCnt + 1
                cavCnt = cavCnt + 1
              )

              ; POLY_CAVITY|<id>|<cav_verts>|<outer_koz_verts>|<inner_safe_verts>
              ; Smooth curved BGA-following non-rectangular Recess & KOZ contours!
              ( rType == "POLY_CAVITY" && length(parts) >= 3
                let( (cavPts kozPts safePts)
                  cavPts  = pdnMrParseVertices(nth(2 parts))
                  kozPts  = if( length(parts) >= 4 then pdnMrParseVertices(nth(3 parts)) else nil )
                  safePts = if( length(parts) >= 5 then pdnMrParseVertices(nth(4 parts)) else nil )

                  when( cavPts && length(cavPts) >= 4
                    axlDBCreateShape(axlPathStart(cavPts 0.0) t "SUBSTRATE GEOMETRY/LSC_CAVITY")
                    axlDBCreatePath(axlPathStart(cavPts 25.0) recessLayer)
                    recessKozCnt = recessKozCnt + 1
                    cavCnt = cavCnt + 1
                  )
                  when( kozPts && length(kozPts) >= 4 && cavPts && length(cavPts) >= 4
                    pdnMrCreatePolyRingShape(kozPts cavPts recessLayer)
                    axlDBCreatePath(axlPathStart(kozPts 25.0) recessLayer)
                    recessKozCnt = recessKozCnt + 2
                    when( axlIsLayer("ROUTE KEEPOUT/BASE")
                      axlDBCreateShape(axlPathStart(kozPts 0.0) t "ROUTE KEEPOUT/BASE")
                    )
                  )
                  when( safePts && length(safePts) >= 4 && cavPts && length(cavPts) >= 4
                    pdnMrCreatePolyRingShape(cavPts safePts recessLayer)
                    axlDBCreatePath(axlPathStart(safePts 20.0) recessLayer)
                    recessKozCnt = recessKozCnt + 2
                  )
                )
              )

              ; LSC_DELETE|<refdes>
              ( rType == "LSC_DELETE" && length(parts) >= 2
                let( (cObj)
                  cObj = axlDBFindByName('component nth(1 parts))
                  when( cObj
                    when( cObj->symbol errset(axlDeleteObject(cObj->symbol) nil) )
                    errset(axlDeleteObject(cObj) nil)
                  )
                )
              )

              ; LSC_PLACE|<refdes>|<symName>|<cx>|<cy>|<rotDeg>|<p1Net>|<p2Net>
              ( rType == "LSC_PLACE" && length(parts) >= 8
                pdnMrPlaceBaseLsc(
                  nth(1 parts)
                  nth(2 parts)
                  float(atof(nth(3 parts)))
                  float(atof(nth(4 parts)))
                  float(atof(nth(5 parts)))
                  nth(6 parts)
                  nth(7 parts)
                  netTbl
                )
              )

              ( rType == "VIA" && length(parts) >= 7
                netStr  = nth(1 parts)
                padName = pdnMrGetPadstack(padTbl nth(2 parts))
                xVal    = float(atof(nth(5 parts)))
                yVal    = float(atof(nth(6 parts)))
                netId   = pdnMrGetOrMakeNet(netTbl netStr)
                if( padName then
                  if( car(errset(axlDBCreateVia(padName list(xVal yVal) netId) nil)) then
                    viaCnt = viaCnt + 1
                  else
                    errCnt = errCnt + 1
                  )
                else
                  errCnt = errCnt + 1
                )
              )

              ( rType == "CLINE" && length(parts) >= 8
                netStr = nth(1 parts)
                subStr = upperCase(nth(2 parts))
                if( subStr == "TOP" then subStr = "SURFACE" )
                if( subStr == "BOTTOM" then subStr = "BASE" )
                wVal   = float(atof(nth(3 parts)))
                x1Val  = float(atof(nth(4 parts)))
                y1Val  = float(atof(nth(5 parts)))
                x2Val  = float(atof(nth(6 parts)))
                y2Val  = float(atof(nth(7 parts)))
                netId  = pdnMrGetOrMakeNet(netTbl netStr)
                lyrSub = strcat("CONDUCTOR/" subStr)
                rPath  = axlPathStart(list(list(x1Val y1Val)) wVal)
                axlPathLine(rPath wVal list(x2Val y2Val))
                if( car(errset(axlDBCreatePath(rPath lyrSub netId) nil)) then
                  clineCnt = clineCnt + 1
                else
                  errCnt = errCnt + 1
                )
              )
            )
          )
        )
      )
      when( curStaticOpen
        errset(axlDBCreateCloseShape(curStaticOpen) nil)
        curStaticOpen = nil
      )
      close(inPort)
    )

    ; Pour all Dynamic Power & VSS Plane Shapes around vias, clines, pins, and manual KOZ voids!
    errset(axlShapeDynamicUpdate(nil t) nil)
    axlDBRefreshId(nil)

    if( saveDesign then
      if( outMcmPath && stringp(outMcmPath) && strlen(outMcmPath) > 0 then
        axlSaveDesign(?design outMcmPath ?noConfirm t)
      else
        axlSaveDesign(?design axlCurrentDesign() ?noConfirm t)
      )
    else
      axlSetVariable("noconfirm" t)
    )

    d = axlDBGetDesign()
    when( reportPath && stringp(reportPath) && strlen(reportPath) > 0
      outP = outfile(reportPath "w")
      when( outP
        let( (verDyn verStat verRecess sgParam)
          verDyn = 0
          verStat = 0
          foreach( lyrName axlGetParam("paramLayerGroup:CONDUCTOR")->groupMembers
            foreach( sh axlDBGetShapes(strcat("CONDUCTOR/" lyrName))
              if( sh->shapeBoundary then
                verDyn = verDyn + 1
              else
                verStat = verStat + 1
              )
            )
          )
          verRecess = length(axlDBGetShapes(recessLayer))

          fprintf(outP "STATUS=%s\n" if( errCnt == 0 then "SUCCESS" else "PARTIAL" ))
          fprintf(outP "POLY_SHAPES_CREATED=%d\n" polyCnt)
          fprintf(outP "DYNAMIC_SHAPES_CREATED=%d\n" dynCnt)
          fprintf(outP "STATIC_GUARD_SHAPES_CREATED=%d\n" staticGuardCnt)
          fprintf(outP "DB_DYNAMIC_CONDUCTOR_SHAPES=%d\n" verDyn)
          fprintf(outP "DB_STATIC_CONDUCTOR_SHAPES=%d\n" verStat)
          fprintf(outP "POLY_VOIDS_CREATED=%d\n" voidCnt)
          fprintf(outP "CAVITIES_CREATED=%d\n" cavCnt)
          fprintf(outP "RECESS_CAVITY_PDN_CREATED=%d\n" recessKozCnt)
          fprintf(outP "DB_RECESS_CAVITY_PDN_SHAPES=%d\n" verRecess)
          fprintf(outP "VIAS_CREATED=%d\n" viaCnt)
          fprintf(outP "CLINES_CREATED=%d\n" clineCnt)
          fprintf(outP "ERRORS=%d\n" errCnt)
        )

        checkNets = list("VDDC0" "VDD_0P8_SRAM_CC0" "VDDQ_0P85_HBM_MEM5" "VDDC_1P0_HBM_MEM5" "VDDQL5" "VPP_1P8_HBM_MEM5" "VSS")
        foreach( cn checkNets
          let( (nObj vc cc sc pc brCnt ratCnt openPinBr floatingBr)
            nObj = axlDBFindByName('net cn)
            vc = 0
            cc = 0
            sc = 0
            pc = 0
            brCnt = if( nObj && nObj->branches length(nObj->branches) 0 )
            ratCnt = if( nObj && nObj->rats length(nObj->rats) 0 )
            openPinBr = 0
            floatingBr = 0

            when( nObj && nObj->branches
              foreach( br nObj->branches
                let( (bp bv bc bs sampleXY inDomain)
                  bp = 0
                  bv = 0
                  bc = 0
                  bs = 0
                  sampleXY = nil
                  foreach( ch br->children
                    case( ch->objType
                      ("via"   vc = vc + 1  bv = bv + 1)
                      ("path"  cc = cc + 1  bc = bc + 1)
                      ("shape" sc = sc + 1  bs = bs + 1)
                      ("pin"   pc = pc + 1  bp = bp + 1  unless( sampleXY sampleXY = ch->xy ))
                    )
                  )
                  if( cn == "VSS" then
                    ; For global VSS, count open single-pin branches strictly inside U9 or U13 routed domains
                    inDomain = sampleXY && (
                      (car(sampleXY) >= -16350.0 && car(sampleXY) <= 16350.0 && cadr(sampleXY) >= 15900.0 && cadr(sampleXY) <= 33250.0) ||
                      (car(sampleXY) >= -46150.0 && car(sampleXY) <= -26700.0 && cadr(sampleXY) >= 22150.0 && cadr(sampleXY) <= 34750.0)
                    )
                    when( inDomain && bp == 1 && bv == 0 && bc == 0 && bs == 0
                      openPinBr = openPinBr + 1
                    )
                  else
                    when( bp == 1 && bv == 0 && bc == 0 && bs == 0
                      openPinBr = openPinBr + 1
                    )
                  )
                  when( bp == 0 && (bv + bc + bs) > 0
                    floatingBr = floatingBr + 1
                  )
                )
              )
            )
            fprintf(outP "DB_NET_%s_PINS=%d\n" cn pc)
            fprintf(outP "DB_NET_%s_VIAS=%d\n" cn vc)
            fprintf(outP "DB_NET_%s_CLINES=%d\n" cn cc)
            fprintf(outP "DB_NET_%s_SHAPES=%d\n" cn sc)
            fprintf(outP "DB_NET_%s_BRANCHES=%d\n" cn brCnt)
            fprintf(outP "DB_NET_%s_RATS=%d\n" cn ratCnt)
            fprintf(outP "DB_NET_%s_OPEN_PIN_BRANCHES=%d\n" cn openPinBr)
            fprintf(outP "DB_NET_%s_FLOATING_BRANCHES=%d\n" cn floatingBr)
          )
        )
        close(outP)
      )
    )
    t
  )
)
