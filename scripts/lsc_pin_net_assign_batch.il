; =============================================================================
; File: lsc_pin_net_assign_batch.il
; Package: agent04_pdn_architect
; Description:
;   Headless Cadence APD 25.1 LSC (Land-Side Capacitor) Pin Net Assignment Engine.
;   Ported & upgraded from legacy GUI `HFC_change_pin_net_bga_lsc.il` and
;   `assign_nets_poly_2_optimize.il` for 100% non-interactive `-nographic` runs.
;
;   Capabilities:
;     1. `pdnCreateOrUpgradeLogicalLsc(refDes symName cx cy mirFlag rotDeg p1Net p2Net netTbl @optional templateCompSym)`
;        - Instantiates a true logical LSC component (`axlDBCreateComponent` +
;          `axlDBCreateSymbol`) or upgrades an unattached mechanical/package LSC
;          symbol (`sym->component == nil`) so both pins accept electrical nets
;          via `axlChangeNet(pinDbid targetNetName)`.
;     2. `pdnAssignPinsOnLscSymbol(symObj p1Net p2Net netTbl)`
;        - Assigns Pin 1 -> `p1Net` and Pin 2 -> `p2Net` (skipping no-op updates
;          when already assigned, and auto-creating missing nets in `netTbl`).
;     3. `pdnDetectNetAtXYOnLayers(px py searchLayers)`
;        - Automatically detects the power/ground net under an LSC pad `(px, py)`
;          by querying touching `12B->BASE` vias or underlying `12B`/`10B` shapes!
;     4. `pdnAssignLscPinNetsBatch(mode mapFile regionBBox vddNet vssNet refLayer saveDesign outMcmPath reportPath)`
;        - Supports 3 batch modes:
;          * `"MAP_FILE"`         : O(1) `makeTable` lookup from pipe-delimited
;                                   `LSC_PIN_MAP|<refdes>|<pin1_net>|<pin2_net>[|<x>|<y>|<rot>|<sym>]`
;          * `"AUTO_FROM_LAYOUT"` : Auto-detects Pin 1 / Pin 2 nets from touching
;                                   `12B->BASE` vias or `CONDUCTOR/12B` islands!
;          * `"REGION_RULE"`      : Assigns all BASE LSCs inside `regionBBox`
;                                   (`list(x1 y1 x2 y2)` or `nil` for full BASE)
;                                   to `Pin 1 = vddNet` and `Pin 2 = vssNet`!
; =============================================================================

procedure( pdnLscEnsureNet( netTbl netName )
  let( (dbNet)
    when( netName && stringp(netName) && strlen(netName) > 0
      dbNet = if( netTbl then netTbl[netName] else nil )
      unless( dbNet
        dbNet = axlDBFindByName('net netName)
        unless( dbNet
          dbNet = axlDBCreateNet(netName)
        )
        when( netTbl && dbNet
          netTbl[netName] = dbNet
          netTbl[upperCase(netName)] = dbNet
        )
      )
      dbNet
    )
  )
)

procedure( pdnFindAnyTemplateLogicalLsc()
  let( (d found sName sLyr)
    d = axlDBGetDesign()
    found = nil
    when( d
      foreach( s d->symbols
        unless( found
          sName = if( s->name then upperCase(s->name) else "" )
          sLyr  = if( s->layer then upperCase(s->layer) else "" )
          when( s->component && (rexMatchp("0201" sName) || rexMatchp("0402" sName) || rexMatchp("CAP" sName)) &&
                (rexMatchp("BASE" sLyr) || rexMatchp("BOTTOM" sLyr) || rexMatchp("SURFACE" sLyr))
            found = s
          )
        )
      )
    )
    found
  )
)

procedure( pdnAssignPinsOnLscSymbol( symObj p1Net p2Net netTbl )
  let( (pins p1Obj p2Obj pNum curNet targetNet okCnt)
    axlSetVariable("logic_edit_enabled" t)
    okCnt = 0
    when( symObj && symObj->pins && length(symObj->pins) >= 2
      pdnLscEnsureNet(netTbl p1Net)
      pdnLscEnsureNet(netTbl p2Net)
      pins = symObj->pins
      p1Obj = nil
      p2Obj = nil
      foreach( p pins
        pNum = if( p->number then sprintf(nil "%s" p->number) else "" )
        cond(
          ( pNum == "1" p1Obj = p )
          ( pNum == "2" p2Obj = p )
        )
      )
      unless( p1Obj p1Obj = nth(0 pins) )
      unless( p2Obj p2Obj = nth(1 pins) )

      foreach( pair list(list(p1Obj p1Net) list(p2Obj p2Net))
        let( (pObj tNet)
          pObj = nth(0 pair)
          tNet = nth(1 pair)
          when( pObj && tNet && strlen(tNet) > 0
            curNet = if( pObj->net && pObj->net->name then pObj->net->name else "" )
            if( curNet == tNet then
              okCnt = okCnt + 1
            else
              if( car(errset(axlChangeNet(pObj tNet) nil)) then
                okCnt = okCnt + 1
              else
                when( car(errset(axlDBAssignNet(pObj tNet) nil))
                  okCnt = okCnt + 1
                )
              )
            )
          )
        )
      )
    )
    (okCnt >= 2)
  )
)

procedure( pdnMakeRoundedRectPathLsc( x1 y1 x2 y2 rad )
  let( (r rpath)
    r = min(float(rad) min((x2 - x1) / 2.0 (y2 - y1) / 2.0))
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

procedure( pdnEnsureLscDeviceFile( actualSymName )
  let( (devName devFile dp psmList padList devList libDir outP)
    libDir = "G:/My Drive/HFC_TO_docs/Library"
    when( isDir(libDir)
      psmList = axlGetVariableList("psmpath")
      unless( member(libDir psmList)
        axlSetVariable("psmpath" cons(libDir psmList))
      )
      padList = axlGetVariableList("padpath")
      unless( member(libDir padList)
        axlSetVariable("padpath" cons(libDir padList))
      )
    )
    devName = strcat("LSC_DEV_" actualSymName)
    devFile = strcat(devName ".txt")
    unless( isFile(devFile)
      outP = outfile(devFile "w")
      when( outP
        fprintf(outP "(DEVICE FILE: %s)\n" devName)
        fprintf(outP "PACKAGE %s\n" actualSymName)
        fprintf(outP "CLASS DISCRETE\n")
        fprintf(outP "PINCOUNT 2\n")
        fprintf(outP "END\n")
        close(outP)
      )
    )
    devList = axlGetVariableList("devpath")
    unless( member("." devList)
      axlSetVariable("devpath" cons("." devList))
    )
    devName
  )
)

procedure( pdnPinIsOnBase( pObj )
  let( (seStr)
    seStr = if( pObj && pObj->startEnd then upperCase(sprintf(nil "%L" pObj->startEnd)) else "" )
    ((rexMatchp("BASE" seStr) || rexMatchp("BOTTOM" seStr)) && !rexMatchp("SURFACE" seStr))
  )
)

procedure( pdnSymbolIs2PinCap( s )
  let( (sName)
    sName = if( s && s->name then upperCase(s->name) else "" )
    ((rexMatchp("0201" sName) || rexMatchp("0402" sName) || rexMatchp("0204" sName) ||
      rexMatchp("LSC" sName) || rexMatchp("CAP" sName)) &&
     s->pins && length(s->pins) == 2)
  )
)

procedure( pdnCreateOrUpgradeLogicalLsc(
  refDes symName cx cy mirFlag rotDeg p1Net p2Net netTbl @optional (templateCompSym nil) (existingUnattachedSym nil)
)
  let( (devType compRes plcRes placedSym actualSymName tryMir)
    axlSetVariable("logic_edit_enabled" t)
    actualSymName = if( symName && strlen(symName) > 0 then symName else
                      if( existingUnattachedSym && existingUnattachedSym->name then existingUnattachedSym->name else
                        if( templateCompSym && templateCompSym->name then templateCompSym->name else "SM0201_690X390X550_01A" ) ) )

    devType = pdnEnsureLscDeviceFile(actualSymName)
    compRes = errset(axlDBCreateComponent(refDes devType) nil)
    unless( compRes && car(compRes)
      compRes = errset(axlDBCreateComponent(refDes devType actualSymName "DISCRETE") nil)
    )

    placedSym = nil
    when( (compRes && car(compRes)) || axlDBFindByName('component refDes)
      when( existingUnattachedSym
        errset(axlDeleteObject(existingUnattachedSym) nil)
      )
      ; Note: In HFC APD libraries, SM0201_690X390X550_01A is authored directly on CONDUCTOR/BASE
      ; (so mir=nil lands on CONDUCTOR/BASE, whereas mir=t flips it onto CONDUCTOR/SURFACE!), while
      ; SM0201S_690X390X220_01C is authored on CONDUCTOR/SURFACE (requiring mir=t for CONDUCTOR/BASE).
      ; Try mir=nil first and verify pin->startEnd; if not on BASE, flip to mir=t automatically!
      tryMir = nil
      plcRes = errset(axlDBCreateSymbol(refDes list(float(cx) float(cy)) tryMir float(rotDeg)) nil)
      when( plcRes && car(plcRes)
        placedSym = if( listp(car(plcRes)) then car(car(plcRes)) else car(plcRes) )
      )
      when( placedSym && placedSym->pins && !pdnPinIsOnBase(car(placedSym->pins))
        errset(axlDeleteObject(placedSym) nil)
        placedSym = nil
        plcRes = errset(axlDBCreateSymbol(refDes list(float(cx) float(cy)) t float(rotDeg)) nil)
        when( plcRes && car(plcRes)
          placedSym = if( listp(car(plcRes)) then car(car(plcRes)) else car(plcRes) )
        )
      )
    )
    when( placedSym
      pdnAssignPinsOnLscSymbol(placedSym p1Net p2Net netTbl)
    )
    placedSym
  )
)

procedure( pdnDetectNetAtXYOnLayers( px py refSubclasses )
  let( (foundNet box obj nName subLyr seStr)
    foundNet = nil
    box = list(list((px - 175.0) (py - 175.0)) list((px + 175.0) (py + 175.0)))

    ; 1. Check touching 12B->BASE vias in pad box first (exact pad-via match!)
    axlClearSelSet()
    axlSetFindFilter(?enabled list("NOALL" "VIAS") ?onButtons list("NOALL" "VIAS"))
    axlAddSelectBox(box)
    foreach( obj axlGetSelSet()
      unless( foundNet
        when( obj->net && obj->net->name && obj->net->name != "" && upperCase(obj->net->name) != "DUMMY"
          seStr = if( obj->startEnd then upperCase(sprintf(nil "%L" obj->startEnd)) else "" )
          when( rexMatchp("BASE" seStr) || rexMatchp("BOTTOM" seStr) || rexMatchp("12B" seStr)
            foundNet = obj->net->name
          )
        )
      )
    )
    axlClearSelSet()

    ; 2. Fallback: check CONDUCTOR/<refLayer> filled copper shapes containing (px, py)
    unless( foundNet
      axlSetFindFilter(?enabled list("NOALL" "SHAPES") ?onButtons list("NOALL" "SHAPES"))
      axlAddSelectPoint(list(px py))
      foreach( obj axlGetSelSet()
        unless( foundNet
          subLyr = if( obj->layer then upperCase(obj->layer) else "" )
          foreach( rSub refSubclasses
            when( !foundNet && rexMatchp(upperCase(rSub) subLyr) && obj->net && obj->net->name && obj->net->name != ""
              nName = obj->net->name
              when( upperCase(nName) != "DUMMY"
                foundNet = nName
              )
            )
          )
        )
      )
      axlClearSelSet()
    )
    foundNet
  )
)

procedure( pdnIsBaseLscSymbol( s )
  (pdnSymbolIs2PinCap(s) && pdnPinIsOnBase(car(s->pins)))
)

procedure( pdnAssignLscPinNetsBatch(
  modeStr mapFilePath regionBBox defaultVddNet defaultVssNet refLayersList saveDesign outMcmPath reportPath
)
  let( (d modeU netTbl refMap coordList tmplSym symsToProcess s sx sy sRef
        scannedCnt updatedCnt upgradedCnt createdCnt skippedCnt failedCnt autoIdx
        p1Net p2Net p1 p2 n1 n2 inPort rawLine line parts outP)

    errset(axlDBControl('drcEnable nil) nil)
    errset(axlDBControl('dynamicFillMode 'disabled) nil)
    axlSetVariable("logic_edit_enabled" t)

    d = axlDBGetDesign()
    modeU = upperCase(or(modeStr "AUTO_FROM_LAYOUT"))
    when( modeU != "MAP_FILE"
      errset(axlVisibleDesign(t) nil)
    )
    netTbl = makeTable("pdnLscNetCache" nil)
    refMap = makeTable("pdnLscRefPinMap" nil)
    coordList = nil
    tmplSym = pdnFindAnyTemplateLogicalLsc()

    scannedCnt  = 0
    updatedCnt  = 0
    upgradedCnt = 0
    createdCnt  = 0
    skippedCnt  = 0
    failedCnt   = 0
    autoIdx     = 1

    ; Parse optional pipe-delimited MAP_FILE:
    ;   CLEAR_BASE_LSC_BBOX|<x1_um>|<y1_um>|<x2_um>|<y2_um>
    ;   CAVITY_OUTLINE|<pocket_id>|<x1_um>|<y1_um>|<x2_um>|<y2_um>|<corner_r_um>|<ext_koz_um>
    ;   LSC_PIN_MAP|<refdes>|<pin1_net>|<pin2_net>[|<x_um>|<y_um>|<rot_deg>|<sym_name>|<CREATE_IF_MISSING>]
    clearedCnt = 0
    cavityCnt  = 0
    when( mapFilePath && stringp(mapFilePath) && strlen(mapFilePath) > 0 && isFile(mapFilePath)
      inPort = infile(mapFilePath)
      when( inPort
        while( gets(rawLine inPort)
          line = buildString(parseString(rawLine "\r\n") "")
          when( strlen(line) > 0 && substring(line 1 1) != "#"
            parts = parseString(line "|")
            when( length(parts) >= 2
              let( (rType)
                rType = upperCase(nth(0 parts))
                cond(
                  ( rType == "CLEAR_BASE_LSC_BBOX" && length(parts) >= 5 && d
                    let( (bx1 by1 bx2 by2 cx0 cy0 sRefU)
                      bx1 = float(atof(nth(1 parts)))
                      by1 = float(atof(nth(2 parts)))
                      bx2 = float(atof(nth(3 parts)))
                      by2 = float(atof(nth(4 parts)))
                      foreach( s d->symbols
                        sRefU = if( s->refdes then upperCase(s->refdes) else "" )
                        when( (pdnIsBaseLscSymbol(s) || rexMatchp("^C_VDDUC" sRefU) || rexMatchp("^C_LSC" sRefU)) && s->xy
                          cx0 = float(car(s->xy))
                          cy0 = float(cadr(s->xy))
                          when( cx0 >= bx1 && cx0 <= bx2 && cy0 >= by1 && cy0 <= by2
                            if( s->component then
                              errset(axlDeleteObject(s->component) nil)
                            else
                              errset(axlDeleteObject(s) nil)
                            )
                            clearedCnt = clearedCnt + 1
                          )
                        )
                      )
                    )
                  )

                  ( rType == "CAVITY_OUTLINE" && length(parts) >= 8
                    let( (cx1 cy1 cx2 cy2 rCav kozExt cPath kPath)
                      cx1    = float(atof(nth(2 parts)))
                      cy1    = float(atof(nth(3 parts)))
                      cx2    = float(atof(nth(4 parts)))
                      cy2    = float(atof(nth(5 parts)))
                      rCav   = float(atof(nth(6 parts)))
                      kozExt = float(atof(nth(7 parts)))
                      unless( axlIsLayer("SUBSTRATE GEOMETRY/LSC_CAVITY")
                        axlLayerCreateNonConductor("SUBSTRATE GEOMETRY/LSC_CAVITY")
                      )
                      cPath = pdnMakeRoundedRectPathLsc(cx1 cy1 cx2 cy2 rCav)
                      axlDBCreateShape(cPath nil "SUBSTRATE GEOMETRY/LSC_CAVITY")
                      when( kozExt > 0.0 && axlIsLayer("ROUTE KEEPOUT/BASE")
                        kPath = pdnMakeRoundedRectPathLsc((cx1 - kozExt) (cy1 - kozExt) (cx2 + kozExt) (cy2 + kozExt) (rCav + kozExt))
                        axlDBCreateShape(kPath t "ROUTE KEEPOUT/BASE")
                      )
                      cavityCnt = cavityCnt + 1
                    )
                  )

                  ( rType == "LSC_PIN_MAP" && length(parts) >= 4
                    let( (mRef mP1 mP2 mX mY mRot mSym mCreate)
                      mRef = nth(1 parts)
                      mP1  = nth(2 parts)
                      mP2  = nth(3 parts)
                      refMap[upperCase(mRef)] = list(mRef mP1 mP2)
                      when( length(parts) >= 6
                        mX = float(atof(nth(4 parts)))
                        mY = float(atof(nth(5 parts)))
                        mRot = if( length(parts) >= 7 then float(atof(nth(6 parts))) else 0.0 )
                        mSym = if( length(parts) >= 8 then nth(7 parts) else "SM0201_690X390X550_01A" )
                        mCreate = if( length(parts) >= 9 then (upperCase(nth(8 parts)) == "YES" || upperCase(nth(8 parts)) == "TRUE") else nil )
                        coordList = cons(list(mRef mP1 mP2 mX mY mRot mSym mCreate) coordList)
                      )
                    )
                  )
                )
              )
            )
          )
        )
        close(inPort)
      )
    )

    ; Collect existing BASE LSC symbols inside optional regionBBox = list(x1 y1 x2 y2)
    symsToProcess = nil
    matchedRefs = makeTable("pdnMatchedLscRefs" nil)
    when( d
      foreach( s d->symbols
        when( pdnIsBaseLscSymbol(s)
          sx = if( s->xy then float(car(s->xy)) else 0.0 )
          sy = if( s->xy then float(cadr(s->xy)) else 0.0 )
          if( regionBBox == nil ||
              (sx >= float(nth(0 regionBBox)) && sx <= float(nth(2 regionBBox)) &&
               sy >= float(nth(1 regionBBox)) && sy <= float(nth(3 regionBBox))) then
            symsToProcess = cons(s symsToProcess)
          )
        )
      )
    )

    foreach( s symsToProcess
      scannedCnt = scannedCnt + 1
      sx = if( s->xy then float(car(s->xy)) else 0.0 )
      sy = if( s->xy then float(cadr(s->xy)) else 0.0 )
      sRef = if( s->refdes && strlen(s->refdes) > 0 then s->refdes else nil )
      p1Net = nil
      p2Net = nil

      cond(
        ( modeU == "MAP_FILE"
          let( (entry bestDist cItem)
            entry = if( sRef then refMap[upperCase(sRef)] else nil )
            if( entry then
              matchedRefs[upperCase(sRef)] = t
              p1Net = nth(1 entry)
              p2Net = nth(2 entry)
            else
              bestDist = 60.0
              foreach( cItem coordList
                let( (dx dy dist)
                  dx = sx - nth(3 cItem)
                  dy = sy - nth(4 cItem)
                  dist = sqrt(dx * dx + dy * dy)
                  when( dist < bestDist
                    bestDist = dist
                    sRef  = nth(0 cItem)
                    p1Net = nth(1 cItem)
                    p2Net = nth(2 cItem)
                    matchedRefs[upperCase(sRef)] = t
                  )
                )
              )
            )
          )
        )

        ( modeU == "REGION_RULE"
          p1 = nth(0 s->pins)
          p2 = nth(1 s->pins)
          ; Check if one pin already touches a VSS via so polarity matches physical vias!
          n1 = if( p1 && p1->xy then pdnDetectNetAtXYOnLayers(float(car(p1->xy)) float(cadr(p1->xy)) list("12B" "BASE")) else nil )
          n2 = if( p2 && p2->xy then pdnDetectNetAtXYOnLayers(float(car(p2->xy)) float(cadr(p2->xy)) list("12B" "BASE")) else nil )
          if( n1 && rexMatchp("VSS" upperCase(n1)) && !(n2 && rexMatchp("VSS" upperCase(n2))) then
            p1Net = or(defaultVssNet "VSS")
            p2Net = or(defaultVddNet "VDDUC0")
          else
            p1Net = or(defaultVddNet "VDDUC0")
            p2Net = or(defaultVssNet "VSS")
          )
        )

        ( t ; AUTO_FROM_LAYOUT
          p1 = nth(0 s->pins)
          p2 = nth(1 s->pins)
          n1 = if( p1 && p1->xy then pdnDetectNetAtXYOnLayers(float(car(p1->xy)) float(cadr(p1->xy)) or(refLayersList list("12B" "10B"))) else nil )
          n2 = if( p2 && p2->xy then pdnDetectNetAtXYOnLayers(float(car(p2->xy)) float(cadr(p2->xy)) or(refLayersList list("12B" "10B"))) else nil )
          p1Net = or(n1 defaultVddNet)
          p2Net = or(n2 defaultVssNet)
          ; Guard against assigning both capacitor terminals to the exact same net!
          when( p1Net && p2Net && upperCase(p1Net) == upperCase(p2Net)
            if( rexMatchp("VSS" upperCase(p1Net)) then
              p1Net = or(defaultVddNet p1Net)
            else
              p2Net = or(defaultVssNet "VSS")
            )
          )
        )
      )

      if( p1Net && p2Net && strlen(p1Net) > 0 && strlen(p2Net) > 0 then
        if( s->component then
          ; Existing logical component — check & assign/update pins by exact pin number ("1" / "2")
          let( (p1o p2o cur1 cur2)
            p1o = nth(0 s->pins)
            p2o = nth(1 s->pins)
            foreach( pp s->pins
              when( pp->number == "1" p1o = pp )
              when( pp->number == "2" p2o = pp )
            )
            cur1 = if( p1o && p1o->net then p1o->net->name else "" )
            cur2 = if( p2o && p2o->net then p2o->net->name else "" )
            if( cur1 == p1Net && cur2 == p2Net then
              skippedCnt = skippedCnt + 1
            else
              if( pdnAssignPinsOnLscSymbol(s p1Net p2Net netTbl) then
                updatedCnt = updatedCnt + 1
              else
                failedCnt = failedCnt + 1
              )
            )
          )
        else
          ; Unattached mechanical/package symbol -> upgrade to logical component + assign nets!
          unless( sRef
            while( axlDBFindByName('component sprintf(nil "C_LSC_AUTO_%04d" autoIdx))
              autoIdx = autoIdx + 1
            )
            sRef = sprintf(nil "C_LSC_AUTO_%04d" autoIdx)
            autoIdx = autoIdx + 1
          )
          let( (sRot sMir newSym)
            sRot = if( s->rotation then float(s->rotation) else 0.0 )
            sMir = if( s->isMirrored then t else t )
            newSym = pdnCreateOrUpgradeLogicalLsc(sRef s->name sx sy sMir sRot p1Net p2Net netTbl tmplSym s)
            if( newSym && newSym->component then
              upgradedCnt = upgradedCnt + 1
            else
              failedCnt = failedCnt + 1
            )
          )
        )
      else
        skippedCnt = skippedCnt + 1
      )
    )

    ; Also create any MAP_FILE rows marked CREATE_IF_MISSING == YES that were not yet in the .mcm!
    when( modeU == "MAP_FILE"
      foreach( cItem reverse(coordList)
        let( (mRef mP1 mP2 mX mY mRot mSym mCreate newS)
          mRef    = nth(0 cItem)
          mP1     = nth(1 cItem)
          mP2     = nth(2 cItem)
          mX      = nth(3 cItem)
          mY      = nth(4 cItem)
          mRot    = nth(5 cItem)
          mSym    = nth(6 cItem)
          mCreate = nth(7 cItem)
          when( mCreate && !matchedRefs[upperCase(mRef)]
            newS = pdnCreateOrUpgradeLogicalLsc(mRef mSym mX mY t mRot mP1 mP2 netTbl tmplSym nil)
            if( newS && newS->component then
              createdCnt = createdCnt + 1
            else
              failedCnt = failedCnt + 1
            )
          )
        )
      )
    )

    axlDBRefreshId(nil)
    d = axlDBGetDesign()

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
        fprintf(outP "STATUS=%s\n" if( failedCnt == 0 then "SUCCESS" else "PARTIAL" ))
        fprintf(outP "MODE=%s\n" modeU)
        fprintf(outP "LSC_CLEARED_PREEXISTING=%d\n" clearedCnt)
        fprintf(outP "LSC_CAVITIES_DRAWN=%d\n" cavityCnt)
        fprintf(outP "LSC_SCANNED=%d\n" scannedCnt)
        fprintf(outP "LSC_PINS_UPDATED=%d\n" updatedCnt)
        fprintf(outP "LSC_UNATTACHED_UPGRADED=%d\n" upgradedCnt)
        fprintf(outP "LSC_NEWLY_CREATED_WITH_NETS=%d\n" createdCnt)
        fprintf(outP "LSC_ALREADY_MATCHED_SKIPPED=%d\n" skippedCnt)
        fprintf(outP "LSC_FAILED=%d\n" failedCnt)
        ; Also verify post-placement BASE layer, rotation, and pin net counts across all MAP_FILE entries!
        when( coordList && d
          let( (verSymCnt verBaseCnt verSurfCnt verP1Cnt verP2Cnt rot0Cnt rot90Cnt rot180Cnt rot270Cnt)
            verSymCnt  = 0
            verBaseCnt = 0
            verSurfCnt = 0
            verP1Cnt   = 0
            verP2Cnt   = 0
            rot0Cnt    = 0
            rot90Cnt   = 0
            rot180Cnt  = 0
            rot270Cnt  = 0
            foreach( s d->symbols
              when( s->refdes && refMap[upperCase(s->refdes)]
                let( (expEntry expP1 expP2 p1o p2o rVal)
                  expEntry = refMap[upperCase(s->refdes)]
                  expP1 = nth(1 expEntry)
                  expP2 = nth(2 expEntry)
                  verSymCnt = verSymCnt + 1
                  rVal = if( s->rotation then round(float(s->rotation)) else 0 )
                  cond(
                    ( rVal == 0 || rVal == 360 rot0Cnt = rot0Cnt + 1 )
                    ( rVal == 90               rot90Cnt = rot90Cnt + 1 )
                    ( rVal == 180              rot180Cnt = rot180Cnt + 1 )
                    ( rVal == 270              rot270Cnt = rot270Cnt + 1 )
                  )
                  when( s->pins && length(s->pins) >= 2
                    p1o = nth(0 s->pins)
                    p2o = nth(1 s->pins)
                    foreach( pp s->pins
                      when( pp->number == "1" p1o = pp )
                      when( pp->number == "2" p2o = pp )
                    )
                    if( pdnPinIsOnBase(p1o) && pdnPinIsOnBase(p2o) then
                      verBaseCnt = verBaseCnt + 1
                    else
                      verSurfCnt = verSurfCnt + 1
                    )
                    when( p1o->net && p1o->net->name == expP1 verP1Cnt = verP1Cnt + 1 )
                    when( p2o->net && p2o->net->name == expP2 verP2Cnt = verP2Cnt + 1 )
                  )
                )
              )
            )
            fprintf(outP "VERIFIED_TARGET_LSCS_IN_DB=%d\n" verSymCnt)
            fprintf(outP "VERIFIED_ON_BASE_LAYER=%d\n" verBaseCnt)
            fprintf(outP "VERIFIED_ON_SURFACE_LAYER=%d\n" verSurfCnt)
            fprintf(outP "VERIFIED_PIN1_NET_MATCHED=%d\n" verP1Cnt)
            fprintf(outP "VERIFIED_PIN2_NET_MATCHED=%d\n" verP2Cnt)
            fprintf(outP "VERIFIED_ROT_0_COUNT=%d\n" rot0Cnt)
            fprintf(outP "VERIFIED_ROT_90_COUNT=%d\n" rot90Cnt)
            fprintf(outP "VERIFIED_ROT_180_COUNT=%d\n" rot180Cnt)
            fprintf(outP "VERIFIED_ROT_270_COUNT=%d\n" rot270Cnt)
          )
        )
        close(outP)
      )
    )
    t
  )
)
