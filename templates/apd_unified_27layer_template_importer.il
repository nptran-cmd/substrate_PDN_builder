; =============================================================================
; File: apd_unified_27layer_template_importer.il
; Package: agent04_pdn_architect/templates
; Description:
;   Unified Designer-Editable 27-Layer (L01 SURFACE -> L27 BASE) Cadence APD 25.1
;   SKILL Batch Importer supporting all 3 PDN Tasks:
;     - Task 1: VDDUC* (LDB U7..U5) & VDDCH* (LDC U2..U1)
;     - Task 2: VDDC* + VDD_0P8_SRAM_CC* (LDA U9, U12, U88, U10)
;     - Task 3: HBM4E 4-Rail (VDDQ + VDDC + VDDQL + VPP on U13..U24 + U41..U52)
;
; Enforces:
;   1. True DYNAMIC copper planes (`axlShapeChangeDynamicType`) + STATIC 150um Guard Bands
;   2. Curved BGA-following non-rectangular Recess KOZ (`POLY_CAVITY`) on
;      `SUBSTRATE GEOMETRY/recess_cavity_pdn`, `SUBSTRATE GEOMETRY/LSC_CAVITY`,
;      and `ROUTE KEEPOUT/BASE`
;   3. Mandatory `CONDUCTOR/BASE` LSC placement (`mir=nil` first + `pin->startEnd`
;      verification + logical `LSC_DEV_<sym>.txt` + `Pin "1"=<VDD>`, `Pin "2"=VSS`)
;   4. Post-Route Database Connectivity & Dynamic Shape Verification Report
; =============================================================================

procedure( pdnTplBuildNetTable()
  let( (d tbl n)
    d = axlDBGetDesign()
    tbl = makeTable("pdnTplNetTbl" nil)
    when( d
      foreach( n d->nets
        when( n->name
          tbl[n->name] = n
          tbl[upperCase(n->name)] = n
        )
      )
    )
    tbl
  )
)

procedure( pdnTplGetOrMakeNet( netTbl netName )
  let( (dbNet)
    if( !netName || netName == "" || netName == "__ISOLATED__" then
      nil
    else
      dbNet = or(netTbl[netName] netTbl[upperCase(netName)])
      unless( dbNet
        dbNet = axlDBFindByName('net netName)
        unless( dbNet dbNet = axlDBCreateNet(netName) )
        when( dbNet
          netTbl[netName] = dbNet
          netTbl[upperCase(netName)] = dbNet
        )
      )
      dbNet
    )
  )
)

procedure( pdnTplBuildSubclassTable()
  let( (tbl s)
    tbl = makeTable("pdnTplSubTbl" nil)
    foreach( s axlSubclasses("CONDUCTOR")
      tbl[s] = s
      tbl[upperCase(s)] = s
    )
    tbl["TOP"] = or(tbl["SURFACE"] "SURFACE")
    tbl["BOTTOM"] = or(tbl["BASE"] "BASE")
    tbl
  )
)

procedure( pdnTplResolveConductorSub( subTbl rawSub )
  let( (clean u found)
    clean = rawSub
    when( rexMatchp("/" clean)
      clean = cadr(parseString(clean "/"))
    )
    u = upperCase(clean)
    if( u == "TOP" then u = "SURFACE" )
    if( u == "BOTTOM" then u = "BASE" )
    found = or(subTbl[clean] subTbl[u] u)
    found
  )
)

procedure( pdnTplGetPadstack( padTbl padName )
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
          ( rexMatchp("2FCI_2BCI" upperCase(padName)) "V282_5_150_282_5_2FCI_2BCI_01B" )
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

procedure( pdnTplParseVertices( vertStr )
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

procedure( pdnTplCreatePolyRing( outerPts innerPts targetLayer )
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

procedure( pdnTplEnsureLscDev( symName )
  let( (cwd devName devFile outP dp)
    cwd = or(axlGetVariable("cwd") ".")
    devName = strcat("LSC_DEV_" symName)
    devFile = strcat(cwd "/" devName ".txt")
    unless( isFile(devFile)
      outP = outfile(devFile "w")
      when( outP
        fprintf(outP "(DEVICE FILE: %s)\nPACKAGE %s\nCLASS DISCRETE\nPINCOUNT 2\nEND\n" devName symName)
        close(outP)
      )
    )
    dp = or(axlGetVariable("devpath") ".")
    unless( rexMatchp(cwd dp) axlSetVariable("devpath" strcat(cwd " " dp)) )
    devName
  )
)

procedure( pdnTplPinIsOnBase( pObj )
  let( (seStr)
    seStr = if( pObj && pObj->startEnd then upperCase(sprintf(nil "%L" pObj->startEnd)) else "" )
    ((rexMatchp("BASE" seStr) || rexMatchp("BOTTOM" seStr)) && !rexMatchp("SURFACE" seStr))
  )
)

procedure( pdnTplPlaceBaseLsc( refDes symName cx cy rotDeg p1Net p2Net netTbl )
  let( (devType compObj plcRes placedSym p1Obj p2Obj pNum)
    devType = pdnTplEnsureLscDev(symName)
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
    when( placedSym && placedSym->pins && !pdnTplPinIsOnBase(car(placedSym->pins))
      errset(axlDeleteObject(placedSym) nil)
      placedSym = nil
      plcRes = errset(axlDBCreateSymbol(refDes list(float(cx) float(cy)) t float(rotDeg)) nil)
      when( plcRes && car(plcRes)
        placedSym = if( listp(car(plcRes)) then car(car(plcRes)) else car(plcRes) )
      )
    )
    when( placedSym && placedSym->pins && length(placedSym->pins) >= 2
      pdnTplGetOrMakeNet(netTbl p1Net)
      pdnTplGetOrMakeNet(netTbl p2Net)
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

procedure( pdnTplCleanU7DomainOnce()
  let( (d s sName sLyr sx sy delList obj nName seStr)
    d = axlDBGetDesign()
    when( d
      foreach( s d->symbols
        sName = if( s->name then upperCase(s->name) else "" )
        sLyr  = if( s->layer then upperCase(s->layer) else "" )
        when( rexMatchp("SM0201" sName) && (rexMatchp("BASE" sLyr) || rexMatchp("BOTTOM" sLyr))
          sx = if( s->xy then float(car(s->xy)) else 0.0 )
          sy = if( s->xy then float(cadr(s->xy)) else 0.0 )
          when( sx >= 13000.0 && sx <= 35500.0 && sy >= -4000.0 && sy <= 36000.0
            errset(axlDeleteObject(s) nil)
          )
        )
      )
    )
    delList = nil
    axlClearSelSet()
    axlSetFindFilter(?enabled list("NOALL" "VIAS" "CLINES") ?onButtons list("NOALL" "VIAS" "CLINES"))
    axlAddSelectBox(list(list(13500.0 -3800.0) list(35200.0 35800.0)))
    foreach( obj axlGetSelSet()
      nName = if( obj->net && obj->net->name then upperCase(obj->net->name) else "" )
      when( nName == "VDDUC0" || nName == "VSS"
        seStr = if( obj->objType == "via" && obj->startEnd then upperCase(sprintf(nil "%L" obj->startEnd)) else "" )
        unless( rexMatchp("C0" seStr) delList = cons(obj delList) )
      )
    )
    axlClearSelSet()
    when( delList errset(axlDeleteObject(delList) nil) )
    t
  )
)

procedure( pdnTplEnsureLibPaths()
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

procedure( pdnRunUnified27LayerTemplateBatch( recipePath outMcmPath reportPath )
  let( (inPort rawLine line parts rType netTbl padTbl subTbl curStaticOpen curDynBndry recessLayer
        cleanedU7 polyCnt dynCnt staticCnt voidCnt cavCnt recessKozCnt lscCnt viaCnt clineCnt errCnt
        subStr netStr shapeMode hasVoids vertField pts rPath lyrSub netId shpRes shpObj
        x1 y1 x2 y2 padName cx cy wVal outP verDyn verStat verRecess checkNets)

    errset(axlDBControl('drcEnable nil) nil)
    errset(axlDBControl('dynamicFillMode 'disabled) nil)
    axlSetVariable("logic_edit_enabled" t)
    pdnTplEnsureLibPaths()

    recessLayer = "SUBSTRATE GEOMETRY/recess_cavity_pdn"
    unless( axlIsLayer(recessLayer) axlLayerCreateNonConductor(recessLayer) )
    unless( axlIsLayer("SUBSTRATE GEOMETRY/LSC_CAVITY") axlLayerCreateNonConductor("SUBSTRATE GEOMETRY/LSC_CAVITY") )

    netTbl = pdnTplBuildNetTable()
    padTbl = makeTable("pdnTplPadTbl" nil)
    subTbl = pdnTplBuildSubclassTable()
    curStaticOpen = nil
    curDynBndry   = nil
    cleanedU7     = nil

    polyCnt      = 0
    dynCnt       = 0
    staticCnt    = 0
    voidCnt      = 0
    cavCnt       = 0
    recessKozCnt = 0
    lscCnt       = 0
    viaCnt       = 0
    clineCnt     = 0
    errCnt       = 0

    inPort = infile(recipePath)
    when( inPort
      while( gets(rawLine inPort)
        line = buildString(parseString(rawLine "\r\n") "")
        when( strlen(line) > 0 && substring(line 1 1) != "#"
          parts = parseString(line "|")
          when( length(parts) >= 1
            rType = upperCase(nth(0 parts))
            cond(
              ; 1. POLY_SHAPE|<layer>|<net>|<DYNAMIC|STATIC_GUARD>|<YES|NO>|<verts>
              ( rType == "POLY_SHAPE" && length(parts) >= 6
                when( curStaticOpen errset(axlDBCreateCloseShape(curStaticOpen) nil) curStaticOpen = nil )
                curDynBndry = nil
                subStr    = pdnTplResolveConductorSub(subTbl nth(1 parts))
                netStr    = nth(2 parts)
                shapeMode = upperCase(nth(3 parts))
                hasVoids  = upperCase(nth(4 parts))
                vertField = nth(5 parts)
                pts = pdnTplParseVertices(vertField)
                when( length(pts) >= 4
                  lyrSub = strcat("CONDUCTOR/" subStr)
                  netId  = pdnTplGetOrMakeNet(netTbl netStr)
                  rPath  = axlPathStart(pts)
                  if( shapeMode == "STATIC_GUARD" || shapeMode == "STATIC_NET" || netStr == "__ISOLATED__" then
                    let( (sNet)
                      sNet = if( shapeMode == "STATIC_GUARD" || netStr == "__ISOLATED__" then nil else netId )
                      if( hasVoids == "YES" then
                        curStaticOpen = car(errset(axlDBCreateOpenShape(rPath t lyrSub sNet) nil))
                        if( curStaticOpen then
                          polyCnt = polyCnt + 1
                          staticCnt = staticCnt + 1
                        else
                          errCnt = errCnt + 1
                        )
                      else
                        if( car(errset(axlDBCreateShape(rPath t lyrSub sNet) nil)) then
                          polyCnt = polyCnt + 1
                          staticCnt = staticCnt + 1
                        else
                          errCnt = errCnt + 1
                        )
                      )
                    )
                  else
                    shpRes = car(errset(axlDBCreateShape(rPath t lyrSub netId) nil))
                    shpObj = if( listp(shpRes) car(shpRes) shpRes )
                    if( shpObj then
                      curDynBndry = car(errset(axlShapeChangeDynamicType(shpObj t nil) nil))
                      if( curDynBndry then
                        polyCnt = polyCnt + 1
                        dynCnt = dynCnt + 1
                      else
                        errCnt = errCnt + 1
                      )
                    else
                      errCnt = errCnt + 1
                    )
                  )
                )
              )

              ; 2. PLANE|<CONDUCTOR/layer or layer>|<net>|<x1>|<y1>|<x2>|<y2>|[YES|NO]
              ( rType == "PLANE" && length(parts) >= 7
                when( curStaticOpen errset(axlDBCreateCloseShape(curStaticOpen) nil) curStaticOpen = nil )
                curDynBndry = nil
                subStr = pdnTplResolveConductorSub(subTbl nth(1 parts))
                lyrSub = strcat("CONDUCTOR/" subStr)
                netStr = nth(2 parts)
                x1 = float(atof(nth(3 parts)))
                y1 = float(atof(nth(4 parts)))
                x2 = float(atof(nth(5 parts)))
                y2 = float(atof(nth(6 parts)))
                netId = pdnTplGetOrMakeNet(netTbl netStr)
                rPath = axlPathStart(list(x1:y1 x2:y1 x2:y2 x1:y2 x1:y1))
                shpRes = car(errset(axlDBCreateShape(rPath t lyrSub netId) nil))
                shpObj = if( listp(shpRes) car(shpRes) shpRes )
                if( shpObj then
                  curDynBndry = car(errset(axlShapeChangeDynamicType(shpObj t t) nil))
                  if( curDynBndry then
                    polyCnt = polyCnt + 1
                    dynCnt = dynCnt + 1
                  else
                    errCnt = errCnt + 1
                  )
                else
                  errCnt = errCnt + 1
                )
              )

              ; 3. POLY_VOID|<verts>
              ( rType == "POLY_VOID" && length(parts) >= 2
                pts = pdnTplParseVertices(nth(1 parts))
                when( length(pts) >= 4
                  rPath = axlPathStart(pts)
                  cond(
                    ( curDynBndry
                      if( car(errset(axlDBCreateVoid(curDynBndry rPath) nil)) then voidCnt = voidCnt + 1 else errCnt = errCnt + 1 )
                    )
                    ( curStaticOpen
                      if( car(errset(axlDBCreateVoid(curStaticOpen rPath) nil)) then voidCnt = voidCnt + 1 else errCnt = errCnt + 1 )
                    )
                  )
                )
              )

              ; 4. PLANE_VOID|<subclass>|<vname>|<x1>|<y1>|<x2>|<y2>
              ( rType == "PLANE_VOID" && length(parts) >= 7 && curDynBndry
                x1 = float(atof(nth(3 parts)))
                y1 = float(atof(nth(4 parts)))
                x2 = float(atof(nth(5 parts)))
                y2 = float(atof(nth(6 parts)))
                rPath = axlPathStart(list(x1:y1 x2:y1 x2:y2 x1:y2 x1:y1))
                if( car(errset(axlDBCreateVoid(curDynBndry rPath) nil)) then voidCnt = voidCnt + 1 else errCnt = errCnt + 1 )
              )

              ; 5. POLY_CLOSE
              ( rType == "POLY_CLOSE"
                when( curStaticOpen errset(axlDBCreateCloseShape(curStaticOpen) nil) curStaticOpen = nil )
                curDynBndry = nil
              )

              ; 6. POLY_CAVITY|<id>|<cav_verts>|<outer_koz_verts>|<inner_safe_verts>
              ( rType == "POLY_CAVITY" && length(parts) >= 3
                let( (cavPts kozPts safePts)
                  cavPts  = pdnTplParseVertices(nth(2 parts))
                  kozPts  = if( length(parts) >= 4 then pdnTplParseVertices(nth(3 parts)) else nil )
                  safePts = if( length(parts) >= 5 then pdnTplParseVertices(nth(4 parts)) else nil )
                  when( cavPts && length(cavPts) >= 4
                    errset(axlDBCreateShape(axlPathStart(cavPts 0.0) t "SUBSTRATE GEOMETRY/LSC_CAVITY") nil)
                    errset(axlDBCreatePath(axlPathStart(cavPts 25.0) recessLayer) nil)
                    cavCnt = cavCnt + 1
                    recessKozCnt = recessKozCnt + 1
                  )
                  when( kozPts && length(kozPts) >= 4 && cavPts && length(cavPts) >= 4
                    pdnTplCreatePolyRing(kozPts cavPts recessLayer)
                    errset(axlDBCreatePath(axlPathStart(kozPts 25.0) recessLayer) nil)
                    recessKozCnt = recessKozCnt + 2
                    when( axlIsLayer("ROUTE KEEPOUT/BASE")
                      errset(axlDBCreateShape(axlPathStart(kozPts 0.0) t "ROUTE KEEPOUT/BASE") nil)
                    )
                  )
                  when( safePts && length(safePts) >= 4 && cavPts && length(cavPts) >= 4
                    pdnTplCreatePolyRing(cavPts safePts recessLayer)
                    errset(axlDBCreatePath(axlPathStart(safePts 20.0) recessLayer) nil)
                    recessKozCnt = recessKozCnt + 2
                  )
                )
              )

              ; 7. LSC_DELETE|<refdes>
              ( rType == "LSC_DELETE" && length(parts) >= 2
                let( (cObj)
                  cObj = axlDBFindByName('component nth(1 parts))
                  when( cObj
                    when( cObj->symbol errset(axlDeleteObject(cObj->symbol) nil) )
                    errset(axlDeleteObject(cObj) nil)
                  )
                )
              )

              ; 8. LSC_PLACE|<refdes>|<sym>|<cx>|<cy>|<rot>|<p1Net>|<p2Net>
              ( rType == "LSC_PLACE" && length(parts) >= 8
                if( pdnTplPlaceBaseLsc(
                      nth(1 parts) nth(2 parts)
                      float(atof(nth(3 parts))) float(atof(nth(4 parts)))
                      float(atof(nth(5 parts))) nth(6 parts) nth(7 parts) netTbl
                    )
                then lscCnt = lscCnt + 1 else errCnt = errCnt + 1 )
              )

              ; 9. LSC_SYM|<refdes>|<sym>|BOTTOM|<cx>|<cy>|<rot>|<p1Net>|<p2Net>|<pocket>
              ( rType == "LSC_SYM" && length(parts) >= 9
                unless( cleanedU7
                  pdnTplCleanU7DomainOnce()
                  cleanedU7 = t
                )
                if( pdnTplPlaceBaseLsc(
                      nth(1 parts) nth(2 parts)
                      float(atof(nth(4 parts))) float(atof(nth(5 parts)))
                      float(atof(nth(6 parts))) nth(7 parts) nth(8 parts) netTbl
                    )
                then lscCnt = lscCnt + 1 else errCnt = errCnt + 1 )
              )

              ; 10. VIA|<net>|<padstack>|<startLyr>|<endLyr>|<x>|<y>|<tag>
              ( rType == "VIA" && length(parts) >= 7
                netStr  = nth(1 parts)
                padName = pdnTplGetPadstack(padTbl nth(2 parts))
                cx      = float(atof(nth(5 parts)))
                cy      = float(atof(nth(6 parts)))
                netId   = pdnTplGetOrMakeNet(netTbl netStr)
                if( padName && car(errset(axlDBCreateVia(padName list(cx cy) netId) nil)) then
                  viaCnt = viaCnt + 1
                  when( mod(viaCnt 100000) == 0 && reportPath && reportPath != ""
                    let( (progP)
                      progP = outfile(strcat(reportPath ".progress") "a")
                      when( progP
                        fprintf(progP "PROGRESS poly=%d cav=%d lsc=%d via=%d cline=%d err=%d\n" polyCnt cavCnt lscCnt viaCnt clineCnt errCnt)
                        close(progP)
                      )
                    )
                  )
                else
                  errCnt = errCnt + 1
                )
              )

              ; 11. CLINE|<net>|<layer>|<width>|<x1>|<y1>|<x2>|<y2>|<tag>
              ( rType == "CLINE" && length(parts) >= 8
                netStr = nth(1 parts)
                subStr = pdnTplResolveConductorSub(subTbl nth(2 parts))
                lyrSub = strcat("CONDUCTOR/" subStr)
                wVal   = float(atof(nth(3 parts)))
                x1     = float(atof(nth(4 parts)))
                y1     = float(atof(nth(5 parts)))
                x2     = float(atof(nth(6 parts)))
                y2     = float(atof(nth(7 parts)))
                netId  = pdnTplGetOrMakeNet(netTbl netStr)
                if( car(errset(axlDBCreateLine(list(x1:y1 x2:y2) wVal lyrSub netId) nil)) then
                  clineCnt = clineCnt + 1
                else
                  errCnt = errCnt + 1
                )
              )
            )
          )
        )
      )
      close(inPort)
    )

    when( curStaticOpen errset(axlDBCreateCloseShape(curStaticOpen) nil) )
    when( reportPath && reportPath != ""
      let( (progP)
        progP = outfile(strcat(reportPath ".progress") "a")
        when( progP
          fprintf(progP "IMPORT_LOOP_DONE poly=%d cav=%d lsc=%d via=%d cline=%d err=%d -> saving pre-pour checkpoint\n" polyCnt cavCnt lscCnt viaCnt clineCnt errCnt)
          close(progP)
        )
      )
    )
    if( outMcmPath && outMcmPath != "" then
      axlSaveDesign(?design outMcmPath ?noConfirm t)
    else
      axlSaveDesign(?design axlCurrentDesign() ?noConfirm t)
    )
    errset(axlDBControl('dynamicFillMode 'smooth) nil)
    errset(axlShapeDynamicUpdate(nil t) nil)
    errset(axlDBControl('drcEnable t) nil)

    if( outMcmPath && outMcmPath != "" then
      axlSaveDesign(?design outMcmPath ?noConfirm t)
    else
      axlSaveDesign(?design axlCurrentDesign() ?noConfirm t)
    )

    when( reportPath && reportPath != ""
      outP = outfile(reportPath "w")
      when( outP
        verDyn = 0
        verStat = 0
        foreach( lyrName axlSubclasses("CONDUCTOR")
          foreach( sh axlDBGetShapes(strcat("CONDUCTOR/" lyrName))
            if( sh->shapeBoundary then verDyn = verDyn + 1 else verStat = verStat + 1 )
          )
        )
        verRecess = length(axlDBGetShapes(recessLayer))

        fprintf(outP "STATUS=%s\n" if( errCnt == 0 then "SUCCESS" else "PARTIAL" ))
        fprintf(outP "DESIGN=%s\n" axlCurrentDesign())
        fprintf(outP "POLYGONS_TOTAL=%d\n" polyCnt)
        fprintf(outP "DYNAMIC_PLANES=%d\n" dynCnt)
        fprintf(outP "STATIC_GUARD_BANDS=%d\n" staticCnt)
        fprintf(outP "DB_DYNAMIC_CONDUCTOR_SHAPES=%d\n" verDyn)
        fprintf(outP "DB_STATIC_CONDUCTOR_SHAPES=%d\n" verStat)
        fprintf(outP "VOIDS=%d\n" voidCnt)
        fprintf(outP "CURVED_CAVITIES=%d\n" cavCnt)
        fprintf(outP "RECESS_CAVITY_PDN_CREATED=%d\n" recessKozCnt)
        fprintf(outP "DB_RECESS_CAVITY_PDN_SHAPES=%d\n" verRecess)
        fprintf(outP "BASE_LSCS_PLACED=%d\n" lscCnt)
        fprintf(outP "VIAS=%d\n" viaCnt)
        fprintf(outP "CLINES=%d\n" clineCnt)
        fprintf(outP "ERRORS=%d\n" errCnt)

        checkNets = list("VDDUC0" "VDDCH0" "VDDC0" "VDD_0P8_SRAM_CC0" "VDDQ_0P85_HBM_MEM5" "VDDC_1P0_HBM_MEM5" "VDDQL5" "VPP_1P8_HBM_MEM5" "VSS")
        foreach( cn checkNets
          let( (nObj vc cc sc pc brCnt ratCnt openPinBr floatingBr)
            nObj = axlDBFindByName('net cn)
            vc = 0 cc = 0 sc = 0 pc = 0
            brCnt = if( nObj && nObj->branches length(nObj->branches) 0 )
            ratCnt = if( nObj && nObj->rats length(nObj->rats) 0 )
            openPinBr = 0 floatingBr = 0
            when( nObj && nObj->branches
              foreach( br nObj->branches
                let( (bp bv bc bs sampleXY inDomain)
                  bp = 0 bv = 0 bc = 0 bs = 0 sampleXY = nil
                  foreach( ch br->children
                    case( ch->objType
                      ("via"   vc = vc + 1  bv = bv + 1)
                      ("path"  cc = cc + 1  bc = bc + 1)
                      ("shape" sc = sc + 1  bs = bs + 1)
                      ("pin"   pc = pc + 1  bp = bp + 1  unless( sampleXY sampleXY = ch->xy ))
                    )
                  )
                  if( cn == "VSS" then
                    inDomain = sampleXY && (
                      (car(sampleXY) >= 13500.0 && car(sampleXY) <= 35500.0 && cadr(sampleXY) >= -4000.0 && cadr(sampleXY) <= 36000.0) ||
                      (car(sampleXY) >= -16350.0 && car(sampleXY) <= 16350.0 && cadr(sampleXY) >= 15900.0 && cadr(sampleXY) <= 33250.0) ||
                      (car(sampleXY) >= -46150.0 && car(sampleXY) <= -26700.0 && cadr(sampleXY) >= 22150.0 && cadr(sampleXY) <= 34750.0)
                    )
                    when( inDomain && bp == 1 && bv == 0 && bc == 0 && bs == 0 openPinBr = openPinBr + 1 )
                  else
                    when( bp == 1 && bv == 0 && bc == 0 && bs == 0 openPinBr = openPinBr + 1 )
                  )
                  when( bp == 0 && (bv + bc + bs) > 0 floatingBr = floatingBr + 1 )
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
