# Bell-teszt előkészítő rendszer — Python kód dokumentáció
A rendszer egy GUI-alapú, kliens-szerver architektúrájú alkalmazás, amely két távoli állomás között koordinálja a Bell-teszt előkészítéséhez szükséges optikai eszközöket (MPC-k, fázistoló lemezek) és az időbélyeg-adatok gyűjtését.

---

## `main_gui.py` — Fő alkalmazás (`App` osztály)

A program belépési pontja. Felépíti a teljes GUI-t, koordinálja az összes modult.

### Inicializálás

**`__init__(root)`**
Felépíti az alkalmazást: inicializálja az állapotváltozókat, felállítja a peer kapcsolatot, csatlakozik a Time Controllerhez, majd megépíti a teljes UI-t.

**`_setup_peer_connection()`**
Megjelenít egy kapcsolódási dialógust, majd a választott szerep (szerver/kliens) alapján létrehozza a `PeerConnection`-t és beállítja a hardver-címeket (TC, FS740). Szerver = Wigner (Computer A), kliens = BME (Computer B).

**`_connect_time_controller()`**
Csatlakozik a helyi Time Controller eszközhöz. Ha a valódi eszköz nem érhető el, mock módba lép.

### Időeltolás kezelés

**`_load_time_offset()` / `_save_time_offset()`**
Betölti/menti az időeltolás értékeket egy JSON konfigurációs fájlból. Támogatja a régi (egyes eltolás) és az új (4 független eltolás) formátumot is.

**`_start_live_calibration_for_pairs(offset_idx)`**
Élő FFT-alapú kalibrációt indít egy adott offset-slothoz. Háttérszálban fut, hogy ne blokkolja a GUI-t. Ez az egyik legfontosabb funkció: a két állomás közötti időeltolást számolja ki a begyűjtött időbélyegekből.

**`_start_live_calibration_for_all_inputs()`**
Az összes csatorna időbélyegét egyetlen nagy tömbbe összefűzi, és arra futtat egy közös FFT-kalibrációt.

**`_apply_calibration_result(offset_idx, result)`**
A kalibrációs eredményt alkalmazza: frissíti a tárolt eltolást, elmenti a konfigfájlba, és értesíti a peer-t az új értékről.

### Streaming vezérlés

**`_on_start_streaming()`**
Elindítja az időbélyeg-streaminget minden konfigurált csatornán, és értesíti a peer-t, hogy azt is elindítsa.

**`_on_stop_streaming(send_to_peer)`**
Leállítja a streaminget, opcionálisan a peer-t is értesíti.

### UI építő metódusok

| Metódus | Feladata |
|---|---|
| `_build_connection_status()` | Kapcsolat állapotát mutató sáv |
| `_build_plot_tab()` | Koincidencia grafikon fül |
| `_build_polarizer_tab()` | MPC/fázislemez optimalizáló fül |
| `_build_time_offset_tab()` | Időeltolás konfiguráló fül |
| `_build_offline_correlation_tab()` | Offline korrelációs fül |
| `_build_live_counters()` | Élő detektor számláló kijelző |
| `_build_correlation_pair_selector()` | Csatorna-pár konfiguráló panel |

### Eszköz optimalizálás

**`_optimize_all_local()` / `_optimize_all_remote()`**
Elindítja az összes helyi, illetve távoli MPC/polarizátor optimalizálását egyszerre.

**`_optimize_one()` / `_optimize_one_cage()`**
Egyetlen kiválasztott eszköz optimalizálását indítja el.

---

## `peer_connection.py` — TCP kapcsolat (`PeerConnection` osztály)

Titkosított, kétirányú TCP kapcsolatot valósít meg a két állomás között. Szerver mód: bejövő kapcsolatot vár. Kliens mód: csatlakozik a szerverhez.

### Kapcsolat felépítése

**`start()`**
A beállított mód alapján elindítja a szervert vagy a klienst.

**`_start_server()`**
Elkezd figyelni a beállított porton, és elindítja a kapcsolatfogadó szálat.

**`_connect_to_server(timeout, retries)`**
Csatlakozik a szerverhez, legfeljebb `retries`-szor próbálkozva. Kapcsolódás után elvégzi a kézfogást, majd elindítja a fogadó és heartbeat szálakat.

### Biztonság — kézfogás

A kapcsolat felépítésekor egy aszimmetrikus kulcscsere és jelszó-alapú hitelesítés történik, mielőtt bármilyen adat átmegy. Ez szükséges, mert a két állomás interneten keresztül kommunikál.

**`_perform_server_handshake()` / `_perform_client_handshake()`**
Elvégzik a biztonságos kézfogást: RSA nyilvános kulcscsere → titkosított session kulcs átadása → hitelesítési kihívás-válasz. Csak sikeres kézfogás után kapcsolódnak a fogadó szálak.

### Kommunikáció

**`send_command(command, data, large)`**
Titkosított JSON üzenetet küld a peer-nek. Szálbiztos: `_send_lock` védi az egyidejű küldésektől. Heartbeat esetén nem-blokkoló zárat használ — ha éppen nagy adat megy, a heartbeat kihagyódik ahelyett, hogy sorban állna.

**`_receiver_loop()`**
Háttérszálban folyamatosan fogadja az üzeneteket. `select()`-et használ időtúllépéshez a `settimeout()` helyett, hogy ne ütközzön a küldő szál saját timeout-jával.

**`_heartbeat_loop()`**
5 másodpercenként keepalive üzenetet küld. Ha 5× heartbeat-intervallumnyi ideig nem érkezik válasz, a kapcsolatot megszakítottnak tekinti.

**`_process_encrypted_message(encrypted_message)`**
Dekódolja a beérkező üzenetet, és meghívja a megfelelő regisztrált kezelőt.

**`register_command_handler(command, handler)`**
Parancs-kezelő függvényt regisztrál egy adott parancshoz.

**`close()`**
Lezárja a kapcsolatot, leállítja az összes szálat.

---

## `live_offset_calibrator.py` — Élő időeltolás kalibrátor (`LiveOffsetCalibrator` osztály)

FFT-alapú keresztkorreláción alapuló időeltolás-számítás, közvetlenül a memóriában tárolt időbélyeg-tömbökre. A fájlba írt verziónál (offline `TimeOffsetCalculator`) 100× gyorsabb és 64× kevesebb memóriát igényel, mert az ismert ~103 µs-os eltoláshoz igazított paramétereket használ.

**FFT paraméterek:**
- τ = 4096 ps (bin szélesség)
- N = 2¹⁷ = 131 072 bin
- Detektálható eltolás tartomány: ±268 µs
- Memóriaigény: ~1 MB (szemben az offline 64 MB-jával)

### Metódusok

**`__init__(tau, N)`**
Inicializálja a kalibrátort a megadott FFT paraméterekkel, és felépíti a belső `TimeOffsetCalculator` objektumot.

**`_build_histogram(timestamps_ps)`**
Nyers pikoszekundumos időbélyeg-tömböt FFT-ready hisztogrammá alakít. Ugyanaz a matematika, mint az offline file-olvasóban.

**`calibrate_pair(local_ts, remote_ts)`**
Két időbélyeg-tömbön FFT keresztkorrelációt futtat, és visszaadja az eltolást pikoszekundumban, a csúcs szignifikanciáját (sigma), és a megbízhatóság minősítését.

**`calibrate_all_pairs(pairs, local_buffers, remote_buffers)`**
Minden aktív offset-slot számára elvégzi a kalibrációt: páronként megkeresi az első pár csatornáit, és arra futtat FFT-t.

**`calibrate_all_as_one(local_buffers, remote_buffers)`**
Az összes helyi és távoli csatorna időbélyegét egyetlen tömbbe fűzi, és egyszerre kalibrálja őket. Gyorsabb, de nem különbözteti meg az egyes offset-slotokat.

### `CalibrationResult` adatosztály

| Mező | Leírás |
|---|---|
| `success` | Sikeres volt-e a kalibráció |
| `offset_ps` | Mért időeltolás pikoszekundumban |
| `peak_sigma` | FFT csúcs szignifikanciája |
| `confidence` | Megbízhatóság: `"High"` / `"Medium"` / `"Low"` / `"Error"` |
| `reliable` | Megbízható-e az eredmény |
| `local_count` / `remote_count` | Feldolgozott időbélyegek száma |
| `elapsed_sec` | Számítási idő másodpercben |

---

## `stream_client.py` — ZMQ timestamp stream (`TimeControllerStreamClient` osztály)

A Time Controller eszköz ZMQ-alapú időbélyeg-streamjéhez csatlakozik. Csatornánként (1–4) külön porton (4242–4245) fogadja az adatokat.

**`__init__(tc_address, is_mock, site_role)`**
Inicializálja a klienst. `is_mock=True` esetén szimulált adatokat generál teszteléshez.

**`start_stream(channel, callback, port)`**
Elindítja az adott csatorna streamjét. A `callback` függvényt hívja meg minden beérkező bináris adatcsomaggal.

**`_detect_stream_socket_type(addr)`**
Megpróbálja kideríteni, hogy a DLT szerver PULL vagy SUB ZMQ socketet használ. PAIR socketet szándékosan nem próbál ki, mert az 1:1 kapcsolat és egy próbacsatlakozás elvágná a valódi klienst.

**`_start_real_stream(channel, callback, port)`**
Csatlakozik a helyi DLT szolgáltatáshoz, automatikusan meghatározza a socket típusát, majd elindítja a stream klienst.

**`_start_mock_stream(channel, callback)`**
Szimulált időbélyeg-generátort indít háttérszálban, 10 Hz-es batch rátával. Teszteléshez hasznos valódi eszköz nélkül.

**`stop_stream(channel)` / `stop_all_streams()`**
Leállítja az adott csatorna, illetve az összes aktív stream-et.

**`is_streaming(channel)`**
Megadja, hogy az adott csatorna éppen streamel-e.

---

## `config.py` — Globális konfiguráció

Az egész program beállításait tárolja. GUI-n kívüli paraméterek itt állíthatók.

| Kategória | Fontosabb változók |
|---|---|
| Hardver címek | `SERVER_TC_ADDRESS`, `CLIENT_TC_ADDRESS`, `SERVER_FS740_ADDRESS`, `CLIENT_FS740_ADDRESS` |
| Mérési alapértékek | `DEFAULT_ACQ_DURATION`, `DEFAULT_BIN_WIDTH`, `DEFAULT_BIN_COUNT` |
| Streaming pufferek | `TIMESTAMP_BUFFER_DURATION_SEC` (30s), `TIMESTAMP_BUFFER_MAX_SIZE` (10M), `TIMESTAMP_BATCH_INTERVAL_SEC` (0.1s) |
| Koincidencia ablak | `COINCIDENCE_WINDOW_PS` (2000 ps) |
| FFT kalibráció | `LIVE_FFT_TAU` (4096 ps), `LIVE_FFT_N` (2²⁰), `CALIBRATION_DURATION_SEC` (90s) |
| TC késleltetések | `TCBME_DELAY*_VALUE`, `TCWIGNER_DELAY*_VALUE` — a két állomás Time Controllereibe küldendő késleltetés értékek |
| Mock mód | `MOCK_TIME_OFFSET_PS`, `MOCK_CHANNEL_OFFSETS_PS` — szimulált időeltolások teszteléshez |
| Eszköz sorozatszámok | `DEFAULT_LOCAL_SERIALS`, `DEFAULT_REMOTE_SERIALS`, `DEFAULT_LOCAL_CAGE_SERIALS`, `DEFAULT_REMOTE_CAGE_SERIALS` |
| Téma | `BG_COLOR`, `FG_COLOR`, `HIGHLIGHT_COLOR`, `PRIMARY_COLOR`, `ACTION_COLOR` |

---

## `plot_updater.py` — Valós idejű mérés és vizualizáció (`PlotUpdater` osztály)

Az élő koincidencia-mérés motorja: kezeli az időbélyeg-puffereket, kiszámítja a koincidenciákat, frissíti a grafikont, és elküldi az adatokat a peer-nek.

### Inicializálás

**`__init__(...)`**
Létrehozza a 4-4 helyi és távoli `TimestampBuffer`-t (csatornánként), a `CoincidenceCounter`-t, és a háttér szálak vezérlő objektumait.

### Streaming vezérlés

**`start(local_save_channels, remote_save_channels, recording_duration_sec)`**
Teljes mérést indít: elindítja a counter display-t (ha még nem fut), meghatározza mock/valódi módot, majd meghívja a `start_streaming()`-et.

**`start_counter_display()`**
Csak a detektor single-rate számláló kijelzőt indítja el, streaming és koincidenciaszámítás nélkül. Az alkalmazás indulásakor automatikusan elindul.

**`start_streaming(tc_address, is_mock, local_save_channels, remote_save_channels)`**
Csatlakozik a Time Controllerhez (vagy mock-hoz), DLT acquisitionöket indít, és elindítja a file-tail szálakat és a küldő szálat.

**`stop_streaming()`**
Leállítja a küldő szálat, a file-tail szálakat, a stream klienseket, a DLT acquisitionöket, és kikapcsolja a TC RAW streamingét.

**`stop()`**
Leállítja a teljes `PlotUpdater`-t: streaming + grafikon frissítő szál.

### Adatfolyam belső metódusok

**`_on_timestamp_batch(channel, binary_data)`**
A stream kliens callback-je: beérkező bináris időbélyeg-csomagot ad hozzá a megfelelő helyi pufferhez.

**`_sender_loop()`**
Dedikált küldő szál: `TIMESTAMP_BATCH_INTERVAL_SEC`-enként (100 ms) elküldi az új időbélyegeket a peer-nek. A lassú grafikon-frissítő ciklustól független szálban fut, hogy a küldés ne késlekedjen.

**`_send_timestamp_batch_to_peer()`**
Az összes csatorna új időbélyegét egyetlen üzenetbe csomagolja (zlib tömörítve, base64 kódolva), és elküldi. Csatornánként max. `MAX_SEND_PER_CH` darabot küld, hogy az első burst ne legyen túl nagy. Sikertelen küldés esetén rollbackeli a nyomkövetőket, hogy legközelebb újra próbálkozzon.

**`_file_tail_worker(channel)`**
Háttérszálban folyamatosan olvassa a DLT által írt fájl végét, és az új időbélyegeket a helyi pufferbe tölti.

**`_update_measurements()`**
Lekéri a TC single-rate számláit, kiszámítja a koincidenciákat, és elküldi a számláló adatokat a peer-nek.

**`_calculate_coincidences()`**
A konfigurált csatornapárokra kiszámítja a koincidencia rátát (count/overlap_sec) a helyi és távoli pufferekben lévő időbélyegekből, az eltolt időtengely figyelembevételével.

**`_draw_plot()` / `_draw_coincidence_plot()`**
Frissíti a matplotlib grafikon megjelenítését.

**`_loop()`**
A háttérszál fő ciklusa: félmásodpercenként meghívja az `_update_measurements()`-t és a `_draw_plot()`-ot.

---

## `optimizer_row_extended.py` — MPC optimalizáló sor (`OptimizerRowExtended` osztály)

Egy sort valósít meg az MPC320 polarizációvezérlő optimalizáló paneljén. Ugyanaz az osztály kezeli a helyi és a távoli eszközöket is.

**`__init__(..., is_remote, peer_connection, ...)`**
Létrehozza a sor UI elemeit és állapotváltozóit. `is_remote=True` esetén a sor a peer állomás eszközét vezérli.

**`_build_widgets(default_serial, default_channel)`**
Felépíti a sor UI elemeit: serial mező, csatorna választó, állapot/szög/érték feliratok, Optimize/Stop gombok. Távoli soroknál kék háttérrel jelzi a különbséget.

**`_on_start()`**
Az "Optimize" gomb kezelője: helyi eszköznél háttérszálban indítja az optimalizálást, távoli eszköznél `OPTIMIZE_START` parancsot küld a peer-nek.

**`_on_stop()`**
A "Stop" gomb kezelője: helyi esetben beállítja a stop eventet, távoli esetben `OPTIMIZE_STOP` parancsot küld.

**`_run_optimization_local()`**
Csatlakozik az MPC320-hoz és a Time Controllerhez, majd meghívja az `optimize_paddles()` optimalizáló függvényt. Hibák esetén státuszt küld a peer-nek is.

**`_run_optimization_remote()`**
`OPTIMIZE_START` parancsot küld a peer-nek a serial és csatorna adatokkal.

**`_on_progress(it, angles, value, best_angles, best_value)`**
Az optimalizáló folyamat visszahívója: frissíti a UI feliratokat, és helyi sor esetén `PROGRESS_UPDATE`-et küld a peer-nek, hogy az is lássa az előrehaladást.

**`handle_remote_progress(data)` / `handle_remote_status(data)`**
A peer-től érkező előrehaladás/státusz üzeneteket alkalmazza a sor UI elemein.

**`cleanup()`**
Leállítja az optimalizálást és lezárja az eszközkapcsolatokat.

---

## `cage_rotator_optimizer_row.py` — Fázislemez optimalizáló

### `optimize_cage_rotator(...)` — önálló függvény

Gradiens-ascent optimalizáló egy cage rotator szögéhez, amely a két TC csatorna között mért visibilityt maximalizálja. Lépésenként numerikus gradienst számít véges különbséggel (`fd_delta_deg`), momentummal simítja az irányt, és adaptívan csökkenti a lépésméretet (`lr_deg`) ha nincs javulás. `patience` iteráció javulás nélkül → megáll.

**Segédfüggvények:**

| Függvény | Feladata |
|---|---|
| `_clip_angle(angle, lo, hi)` | Szöget a megengedett tartományra korlátozza |
| `_measure_counts(tc, channel, samples)` | TC csatorna detektor számát olvassa ki, átlagolja |
| `_measure_visibility(tc, channel_a, channel_b, samples)` | Két csatorna alapján visibilityt számít |
| `_parse_channel_spec(spec)` | `"L1"` / `"R2"` formátumú csatornaspecifikációt értelmez |

### `CageRotatorOptimizerRow` osztály

Fázislemez (cage rotator) optimalizáló sor a GUI-ban. Felépítése és működése megegyezik az `OptimizerRowExtended`-del, de:
- Egyetlen szöget (nem 3 MPC lapátszöget) kezel
- Visibilityt optimalizál (nem single rátát)
- Az optimalizáló függvénye az `optimize_cage_rotator()`

Metódusai (`_on_start`, `_on_stop`, `_run_optimization_local`, `_run_optimization_remote`, `handle_remote_progress`, `handle_remote_status`, `cleanup`) azonos logikát követnek mint az `OptimizerRowExtended`-ben, `CAGE_OPTIMIZE_START` / `CAGE_OPTIMIZE_STOP` / `CAGE_PROGRESS_UPDATE` / `CAGE_STATUS_UPDATE` parancsokkal.

---

## `peer_command_handlers.py` — Peer parancskezelők (`PeerCommandHandlers` osztály)

Központosítja az összes bejövő peer parancs kezelőjét. Az `App` példányra kap referenciát, és azon keresztül éri el a sor objektumokat, puffereket, UI elemeket.

**`register_all(peer_connection)`**
Egyszerre regisztrál minden kezelőt a `PeerConnection`-ba.

### Regisztrált parancsok

| Parancs | Kezelő | Leírás |
|---|---|---|
| `OPTIMIZE_START` | `handle_optimize_start` | Elindítja a helyi MPC optimalizálást a megadott row indexen |
| `OPTIMIZE_STOP` | `handle_optimize_stop` | Megállítja a helyi MPC optimalizálást |
| `STATUS_UPDATE` | `handle_status_update` | Frissíti a távoli sor státusz feliratát |
| `PROGRESS_UPDATE` | `handle_progress_update` | Frissíti a távoli sor előrehaladás adatait |
| `CAGE_OPTIMIZE_START/STOP` | `handle_cage_optimize_*` | Cage rotator optimalizálás indítás/leállítás |
| `CAGE_STATUS/PROGRESS_UPDATE` | `handle_cage_*_update` | Cage rotator UI frissítés |
| `STREAMING_START` | `handle_streaming_start` | Elindítja a helyi streaminget a peer által küldött beállításokkal |
| `STREAMING_STOP` | `handle_streaming_stop` | Leállítja a helyi streaminget, opcionálisan auto-transzfert indít |
| `TIMESTAMP_BATCH` | `handle_timestamp_batch` | Base64+zlib dekódolt időbélyeg tömböt ad a remote pufferekhez |
| `COUNTER_DATA` | `handle_counter_data` | Frissíti a remote detektor számláló értékeket |
| `SAVE_SETTINGS_UPDATE` | `handle_save_settings_update` | Szinkronizálja a mentési checkbox állapotokat a peer beállításai alapján |
| `SAVE_SETTINGS_REQUEST` | `handle_save_settings_request` | A peer kérésére frissíti a helyi mentési beállításokat |
| `APPLY_SERVER_TC_DELAYS` | `handle_apply_server_tc_delays` | Csak szerver oldalon: TC késleltetési parancsokat küld a Time Controllernek |

**Megjegyzés az index-leképezésről:** Az MPC sorok 0–3 indexe a helyi oldalon 4–7-re mappolódik a remote oldalon (és fordítva), mert mindkét oldal ugyanolyan sorrendben tárolja a saját sorait 0-tól kezdve. A cage rotator soroknál ez 0–1 ↔ 2–3.

---

## `file_transfer_manager.py` — Fájlátvitel (`FileTransferManager` osztály)

A rögzített időbélyeg fájlokat darabokban (chunk) küldi át a peer kapcsolaton. Szükséges, mert a mérési fájlok több száz MB-osak lehetnek.

**`__init__(peer_connection, plot_updater, status_callback)`**
Inicializálja az átvitel állapotát és a szükséges referenciákat.

**`request_remote_files()`**
`FILE_TRANSFER_REQUEST` parancsot küld a peer-nek, amellyel kéri a nemrég rögzített fájlokat.

**`handle_transfer_request(data)`**
A peer fájlkérésére reagál: háttérszálban megkeresi a rögzített fájlokat és elindítja a küldést.

**`_send_files_background(data)`**
Háttérszálban végigmegy a rögzített csatorna-fájlokon, és `_send_file_chunked()`-ot hív minden fájlra.

**`_send_file_chunked(channel, filepath)`**
Egyetlen fájlt küld el darabokban: `FILE_TRANSFER_START` → N × `FILE_TRANSFER_CHUNK` → `FILE_TRANSFER_END`. Minden chunk előtt megvárja az ACK-et, hogy ne árassza el a hálózatot.

**`handle_transfer_start(data)` / `handle_transfer_chunk(data)` / `handle_transfer_end(data)`**
A fogadó oldal kezelői: létrehozzák a fájlt, hozzáfűzik a darabokat, majd befejezik és validálják az átvitelt.

**`handle_chunk_ack(data)`**
Chunk nyugtát fogad — feloldja a küldő szál várakozását.

**`get_remote_files()` / `clear_remote_files()`**
Visszaadja / törli a fogadott fájlok listáját.

---

## `time_offset_tab.py` — Offline korreláció fül (`TimeOffsetTab` osztály)

GUI fül a korábban rögzített időbélyeg-fájlokon végzett FFT-alapú időeltolás-számításhoz. Funkcionálisan megegyezik a C++ Correlator-ral.

**`__init__(...)`**
Felépíti a fület, betölti az alapértelmezett FFT paramétereket a konfigból.

**`_build_file_selection(parent)` / `_build_channel_row(parent, ch_idx)`**
Fájlkiválasztó UI: csatornánként local/remote oldalpár, böngésző gombbal.

**`_build_parameters(parent)`**
τ (bin szélesség) és N (bin szám) FFT paraméter mezők, és a Tshift eltolás mező.

**`_auto_detect_files()`**
A legutóbb rögzített fájlokat automatikusan beilleszti a megfelelő csatorna mezőkbe.

**`_start_calculation()`**
Elindítja az FFT keresztkorreláció számítást háttérszálban, hogy ne blokkolja a GUI-t.

**`_on_calculation_complete(result)`**
A háttérszál befejezésekor frissíti az eredmény mezőket (offset értékek, sigma, megbízhatóság) és a preview grafikont.

**`_update_preview_plot(result)`**
A korrelációs függvényt és a csúcsot jeleníti meg a fülön belüli mini grafikonon.

**`_show_correlation_plot()`**
Egy külön matplotlib ablakban mutatja a teljes korrelációs függvényt.

**`_save_to_config()`**
A kiszámított offset értéket elmenti a `time_offset_config.json` fájlba, és frissíti a fő alkalmazást.

**`_copy_to_clipboard()`**
Az offset értéket a vágólapra másolja.

---

## `device_hander.py` — Hardver eszközvezérlők

A Thorlabs Kinesis SDK-n keresztül vezérli a fizikai optikai eszközöket. A Kinesis könyvtárak csak Windows alatt elérhetők, és nem szálbiztosak — ezért globális lock védi az egyidejű csatlakozásokat.

### `MPC320Controller` — Motorized Polarization Controller

**`__init__(serial_no, tc_input_to_watch)`**
Tárolja a sorozatszámot és a figyelendő TC csatornát.

**`connect()`**
Csatlakozik az MPC320 eszközhöz a Thorlabs Kinesis SDK-n keresztül. Globális lockot használ, mert a Kinesis eszközlista-építés (`BuildDeviceList`) nem szálbiztos — párhuzamos csatlakozás korruptálná a device managert.

**`move_to(angle_deg, paddle)`**
Egy lapátot a megadott szögre forgat. A szöget .NET `Decimal` típusra konvertálja, amit a Kinesis API megkövetel.

**`move_to_three(angles_deg)`**
Mindhárom lapátot sorban (szekvenciálisan) forgatja a megadott szögekre. Párhuzamos hívás nem lehetséges, mert a Kinesis COM hívások nem szálbiztosak.

**`home_all()`**
Mindhárom lapátot home pozícióba küldi. Ha a Home parancs sikertelen, 0 fokra próbál mozgatni fallbackként.

**`disconnect()`**
Leállítja a pollingot és lecsatlakozik az eszközről. Először `force=True`-val próbál lecsatlakozni, ha az sem sikerül, `force=False`-szal.

**`get_paddles()`**
Visszaadja a három lapát (`Paddle1`, `Paddle2`, `Paddle3`) Kinesis enum értékeit.

**`search_for_optimal_roations()`**
Félkész implementáció: a `PaddleOptimizer`-t használva megpróbálja megtalálni az optimális lapát szögeket. Valószínűleg hibás/hiányos állapotban van.

---

### `TimeController` — IDQ Time Controller wrapper

**`__init__(address, counters, integration_time_ps)`**
Tárolja a TC IP-címét, a figyelendő számláló indexeket, és az opcionális integrációs időt.

**`connect()`**
ZMQ-n keresztül csatlakozik a Time Controllerhez. Ha `integration_time_ps` meg van adva, azonnal beállítja az akvizíciót.

**`query_counter(idx)`**
Lekéri az adott csatorna aktuális detektor számát (`INPUt{idx}:COUNter?`).

**`query_all_counters()`**
Mind a négy csatorna számlálóját egyszerre kérdezi le, 4-elemű tuple-ként adja vissza.

**`close()`**
Lezárja a ZMQ kapcsolatot. Először `close(0)`-val próbál (linger=0), majd sima `close()`-zal fallbackként.

---

### `CageRotatorController` — Thorlabs K10CR1 forgóasztal

**`connect()`**
Csatlakozik a cage rotatorhoz, betölti a motor konfigurációt (`K10CR1` profil), és megvárja a beállítások inicializálását.

**`move_to(angle_deg, timeout_ms)`**
A forgóasztalt a megadott szögre mozgatja. A szöget .NET `Decimal`-ra konvertálja.

**`home(timeout_ms)`**
Home pozícióba küldi az eszközt. Ha sikertelen, 0 fokra mozgat fallbackként.

**`get_position()`**
Visszaadja az aktuális pozíciót fokokban. A .NET `Decimal` értéket stringen keresztül konvertálja Python `float`-tá, mert közvetlen konverzió nem megbízható.

**`disconnect()`**
Leállítja a pollingot és lecsatlakozik. Azonos logika mint az `MPC320Controller.disconnect()`-nél.

**`__enter__` / `__exit__`**
Context manager támogatás: `with CageRotatorController(...) as ctrl:` szintaxissal használható, automatikus lecsatlakozással.

---

# C++ kód dokumentáció

A C++ kódcsomag a `cpp` almappában található. Fő feladata a fázistoló lemezek (wave plate-ek) optimalizálása a két állomás közötti visibility maximalizálásához, GPS-szinkronizált adatgyűjtéssel és FFT-alapú korrelációval.

---

## `KinesisUtil.cpp` — Fázislemez vezérlő (`KinesisUtil` osztály)

A Thorlabs Kinesis SDK ISC (Integrated Stepper Controller) interfészén keresztül vezérli a lineáris/forgó motorokat (elsősorban a fázistoló lemezeket).

**`connect()`**
Megnyitja a kapcsolatot az eszközzel a sorozatszám alapján.

**`load()`**
Betölti az eszköz beállításait és lekéri a sebesség/gyorsulás paramétereket. Enélkül egyes funkciók nem futnak le, illetve a motor nagyon lassan forog. A beállítások forrása nem teljesen tisztázott (valószínűleg a Kinesis szoftver által mentett profil).

**`startPolling(milisec)` / `stopPolling()`**
Elindítja/leállítja az eszköz állapotának rendszeres lekérdezését.

**`clear()`**
Törli az üzenetsorból a várakozó üzeneteket.

**`home()`**
Home pozícióba állítja az eszközt, majd megvárja a befejezést (`wait_for_command`).

**`wait_for_command(type, id)`**
Blokkoló várakozás egy adott Kinesis üzenetre. A generic motor eszközöknél: type=2 mindig, id=0 home-hoz, id=1 mozgáshoz.

**`moveToPosition(degree)` / `setAbsParam(degree)` + `moveAbs()`**
Abszolút pozícióba mozgás. A `moveToPosition` egy lépésben, a `setAbsParam`+`moveAbs` kétlépéses verzió (utóbbi megvárja a befejezést).

**`setRelParam(degree)` + `moveRel()`**
Relatív elmozdulás beállítása és végrehajtása.

**`setJogStep(step)` / `jog()` / `setJogMode(mode)`**
Jog (lépésenkénti) mozgás beállítása és indítása.

**`stopMoving(mode)`**
Mozgás leállítása: `MOT_Immediate` (azonnali) vagy `MOT_Profiled` (lassítással).

**`setVelParams(acceleration, maxspeed)`**
Sebesség és gyorsulás beállítása. A mértékegységek értelmezése nem teljesen tisztázott.

**`getDevice(real, unitType)` / `getReal(device, unitType)`**
Valós érték ↔ eszköz belső egység konverzió. unitType: 0=távolság, 1=sebesség, 2=gyorsulás.

**`getPos()`**
Aktuális pozíció lekérése fokokban.

**`canMove()`**
Megadja, hogy az eszköz mozoghat-e home nélkül.

---

## `fs_util.cpp` — GPS óra és segédfunkciók (`FSUtil` osztály)

A Stanford Research Systems FS740 GPS-vezérelt oszcillátor/óra vezérlését és a kapcsolódó időzítési funkciókat valósítja meg. A kapcsolat TCP/IP-en, SCPI protokollon (port 5025) keresztül épül fel.

**`init_tcpip()`**
Windows Socket könyvtár inicializálása (WSAStartup).

**`fs740_connect(ip)`**
TCP kapcsolatot épít fel az FS740 GPS óra IP-jéhez (port 5025).

**`fs740_close()` / `fs740_write(str)` / `fs740_read(buffer, num)`**
Alacsony szintű socket küldés/fogadás. Az `fs740_read` `select()`-et használ timeout-hoz.

**`wait_until(t)`**
Blokkol amíg el nem éri a megadott GPS időpontot. Polling módszerrel működik: folyamatosan lekérdezi a GPS órát és összehasonlítja az időponttal. Tesztelések alapján ez a legpontosabb várakozási mód (mikroszekundum pontosságú), szemben a `thread::sleep_for`-ral.

**`start_time()`**
A jelenlegi GPS időpontnál 2 másodperccel későbbi időpontot ad vissza, amelyet a mérés kezdőidőpontjaként használnak. A törtmásodperc részt `.000000000000`-ra állítja, hogy a lehető legközelebb legyen a következő másodperc elejéhez.

**`measure_setup()`**
Előkészíti a GPS órát a méréshez: 1 Hz-es, 10 ns szélességű impulzust konfigurál a 3-as kimeneten (`SOUR3`). Ez lesz a Time Tagger szinkronizáló jele.

**`print_gpstime()`**
Stringként adja vissza az aktuális GPS időpontot (`HH,MM,SS.picoseconds` formátumban).

**`is_earlier_time(early, late)`**
Megmondja hogy az `early` időpont korábbi-e a `late`-nél.

**`calculate_time_diff(buff1, buff2)`**
Két `HH,MM,SS.picoseconds` formátumú időpont különbségét adja vissza pikoszekundumban.

**`run(path)`**
`.exe` vagy `.py` fájlt futtat `CreateProcess`-szel. Python szkript esetén automatikusan `python` parancsot illeszt elé.

**`scpi_terminal()`**
Interaktív SCPI parancssor az FS740-hez, teszteléshez.

**`measure_timedrift(steps)` / `precise_computer_time()` / `write_diff_to_file(delta)`**
Tesztelési segédfunkciók: a gép órájának és a GPS óra idejének összehasonlítása, az eltérés CSV fájlba mentése.

**`is_same_str(str1, str2)` / `is_in(str, substr)`**
String segédfüggvények.

---

## `Correlator.cpp` — FFT keresztkorreláció (`Correlator` osztály)

Bináris időbélyeg fájlokból FFT-alapú keresztkorrelációval meghatározza a két állomás közötti időeltolást. Azonos matematikai elveken alapul mint a Python `TimeOffsetCalculator`.

### Adatbeolvasás

**`read_data(filePath, buffId, tau, chunkSize, N, ...)`**
Bináris fájlból beolvassa az időbélyegeket és hisztogrammá alakítja őket. Az adatok formátuma: páronként `(pikoszekundum, referencia_másodperc)` uint64 értékek — az abszolút időpont = pikoszekundum + referencia_másodperc × 10¹².

**`copyFiles(inputPaths, outputPath, delay)`**
Több kisebb fájlt összefűz egy nagyobb fájlba. A `delay` opcionálisan hozzáadható minden értékhez (teszteléshez maradt benne, éles használatban 0).

### Korrelációs algoritmus

**`runCorrelation(reducStr, dataset1Path, dataset2Path, tauInput)`**
A teljes korrelációs folyamatot futtatja: fájlok összefűzése → opcionális zajszűrés → FFT hisztogramok feltöltése → `CalculateDeltaT` → eredmény pikoszekundumban.

**`CalculateDeltaT(N)`**
FFT keresztkorrelációt számít a két hisztogramból: mindkét buffert FFT-vel transzformálja, szorzatot képez a frekvenciatérben, majd inverz FFT-vel visszatransz­formálja. A korrelációs csúcs helyéből (`rmax`) visszaszámítja az időeltolást.

### Zajszűrés

**`noise_reduc_bound(fp1, fp2)`**
A kisebb fájl minden időbélyegéhez egy `±bound_size` szélességű ablakot számít (a becsült késleltetéssel eltolva), majd a nagyobb fájlból törli azokat az értékeket amelyek egyik ablakba sem esnek bele. Célja: csak azokat az eseményeket tartja meg amelyeknek megvan a párjuk a másik állomáson.

**`is_target_in_bound(arr, size, target)`**
Bináris kereséssel ellenőrzi, hogy egy érték beleesik-e valamelyik határpárba.

**`delete_marked_values(fname)`**
A `marked` vektorban felsorolt indexű értékeket törli a fájlból: először egy temp fájlba másolja a megmaradó adatokat, majd visszaírja az eredetibe.

### Segédfüggvények

| Függvény | Feladata |
|---|---|
| `histogram(v, N, h, Nbin, Tbin)` | Időkülönbség hisztogramot épít egymást követő időbélyegek különbségéből |
| `hist_norm(hin, hout, Nbin)` | Hisztogramot normalizál (területre osztja) |
| `vec_mean(v, n)` / `vec_variance(v, vmean, n)` | Átlag és szórás számítás |
| `rmax(v, N)` / `rmin(v, N)` | Maximum/minimum keresés és helye |
| `dTmean(v, N)` | Egymást követő időbélyegek átlagos különbsége |
| `get_file_size(fname)` | Fájl mérete byte-ban |
| `print_hist` / `print_uintvec` / `print_cvec` / `print_rvec` | Debug kiírások |

---

## `tcp_server.cpp` — Szerver (Wigner állomás)

A Wigner intézet gépén futó szerver program. Fogadja a kliens parancsait, vezérli a helyi fázistoló lemezeket (wigner2: λ/2, wigner4: λ/4), és elküldi a mért adatokat.

### Főbb parancsok (fogadott a klienstől)

| Parancs | Hatás |
|---|---|
| `setup` | GPS óra és Time Tagger előkészítése méréshez |
| `home` | Mindkét fázislemez home pozícióba |
| `clear` | Data mappa kiürítése |
| `start <idő>` | Megvárja a GPS időpontot, lefuttatja `timestamps_acquisition_wigner.py`-t |
| `rotate wigner2 full_phase <időtartam> <idő>` | λ/2 lemezt 180°-on végigforgatja mérés közben |
| `rotate wigner2 fine_scan <időtartam> <idő>` | λ/2 lemezt finom scan módban mozgatja |
| `rotate wigner2 <szög>` | λ/2 lemezt adott szögre állítja |
| `rotate wigner4 <szög>` | λ/4 lemezt adott szögre állítja |
| `read_data_file` | Wigner adatfájlokat darabokban elküldi a kliensnek |
| `read_correlator_buffer` | A helyi korrelációs FFT buffert elküldi a kliensnek |

### Segédfüggvények

**`sendFile(clientSocket, filePath)`**
Fájlt küld 3 bájtos fejléccel tagolt csomagokban, `EOF <fájlnév>` zárójellel.

**`sendFftwBuffer(socket, correlator)`**
Az FFTW komplex buffert küldi el szintén 3 bájtos fejléccel, `EOF` zárójellel.

**`clampData(folder, time_elapsed)`**
A megadott időpontnál újabb időbélyegeket kitörli az adatfájlokból — csak a mérési időablakba eső adatok maradnak meg.

**`sendDoneMessage(clientSocket)`**
`"done"` üzenetet küld minden parancs végrehajtása után, hogy a kliens tudja mikor mehet tovább.

**`clearDataFolder(folder)` / `collectFiles(folder, condition)` / `deleteFiles(folder, condition)`**
Mappa- és fájlkezelő segédfüggvények.

---

## `tcp_client.cpp` — Kliens (BME állomás) és `Orchestrator`

A BME gépén futó kliens program. Kapcsolódik a szerverhez, vezérli a helyi fázislemezeket (bme2: λ/2, bme4: λ/4), fogadja az adatokat, és az `Orchestrator`-on keresztül automatikusan irányítja az optimalizálási folyamatot.

**Indítás:** `client.exe <szerver_ip> [--manual | -m]`

Manuális módban (`-m`) a felhasználó kézzel írhatja be a parancsokat. Automatikus módban az `Orchestrator` generálja a következő lépést.

### Segédfüggvények

**`recvAll(socket, buffer, length)`**
Garantáltan fogad pontosan `length` bájtot (a `recv` nem mindig adja vissza az összeset egyszerre).

**`WaitForCommandDone(socket)`**
Blokkolva vár amíg a szerver `"done"` üzenetet küld.

**`readReceivingFile(socket, firstChunk, firstChunkSize)`**
Fájlt fogad a szervertől csomagokban, `EOF <fájlnév>` jelzésig. A fájlt a neve alapján a data mappába menti.

**`readFftwBuffer(socket, firstChunk, firstChunkSize, N)`**
FFTW buffert fogad a szervertől, összerakja a darabokat, és `fftw_complex*` pointerrel adja vissza.

---

## `orchestrator.cpp` — Optimalizálás vezérlője (`Orchestrator` osztály)

Állapotgép amely automatikusan irányítja a teljes optimalizálási folyamatot. A `runNextStep()` minden hívásra a következő lépést hajtja végre és visszaad egy parancsot, amelyet a kliens elküld a szervernek.

### Optimalizálási lépések sorrendje

```
HomeAll → Setup → MeasureFullPhase → ReadData → AnalyzeData
→ RotateToMinVis → AdjustQWP (iteratívan) → MeasureWithQWP
→ AnalyzeQWPData → ProcessQWPResults → CheckConvergence
→ (konvergált: Exit | nem konvergált: vissza MeasureFullPhase-hez)
```

### Lépések

**`stepHomeAll()`**
Mindkét helyi lemezt home pozícióba állítja.

**`stepSetup()`**
Kitörli az adatmappát.

**`stepMeasureFullPhase()`**
GPS időpontot rögzít, `"rotate wigner2 full_phase <időtartam> <idő>"` parancsot küld — a λ/2 lemez 180°-on végigmegy, közben mindkét oldal gyűjti az adatokat.

**`stepReadData()`**
`"read_data_file"` parancsot küld a szervernek, amely visszaküldi a Wigner adatfájlokat.

**`stepAnalyzeData()`**
Meghívja az `analyzeCoincidences()`-t: koincidenciákat keres a BME és Wigner fájlok között, szögbinekbe sorolja őket, és kiszámítja a visibilityt.

**`stepRotateToMinVis()`**
Megkeresi a minimális koincidencia szögét és oda forgatja a λ/2 lemezt (ez lesz az optimalizálás kiindulópontja a λ/4-hez).

**`stepAdjustQWP()`**
A λ/4 lemez következő tesztszögét állítja be. Először durva scan (coarse), majd finom scan (fine) mindkét állomáson.

**`stepMeasureWithQWP()` / `stepAnalyzeQWPData()`**
Adatgyűjtés és kiértékelés az aktuális λ/4 szögnél.

**`stepProcessQWPResults()`**
Frissíti a legjobb λ/4 szöget, majd eldönti a következő lépést: finom scan → másik oldal → konvergencia ellenőrzés.

**`stepCheckConvergence()`**
Ha a visibility változása kisebb mint `visibilityThreshold`, az optimalizálás sikeresen befejeződött. Egyébként új teljes fázismérést indít.

### Analízis segédfüggvények

**`analyzeCoincidences()`**
Összegyűjti a BME és Wigner fájlokat, koincidenciákat keres (`findCoincidences`), szögbinekbe sorolja (`binCoincidencesByAngle`), és kiszámítja a visibilityt (`computeVisibility`).

**`findCoincidences(clientTimestamps, serverTimestamps, tolerancePico)`**
Két rendezett időbélyeg listán kétmutatós algoritmussal keresi az egyező párokat a megadott tolerancián belül. Az eltolást (`stationTimeOffset`) figyelembe veszi.

**`binCoincidencesByAngle(coincidenceTimestamps, rotationSpeed)`**
Az időbélyegből visszaszámítja a lemez szögét (eltelt idő × forgási sebesség), és a megfelelő szögbinbe számolja.

**`computeVisibility()`**
Visibility = (C_max - C_min) / (C_max + C_min), ahol C_max és C_min a koincidencia eloszlás maximuma és minimuma.

**`parseGPSTime(gpsTimeStr)`**
GPS időpontot (`HH,MM,SS.picoseconds`) abszolút pikoszekundum értékre alakít.

**`loadTimestampsFromFile(filepath)`**
Bináris fájlból beolvassa az időbélyegeket `(pikoszekundum, referencia_másodperc)` párokban.
