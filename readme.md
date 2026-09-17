# Readme

Az alábbi projekt azért készült, hogy előkészítse az optikai eszközöket egy Bell-teszt számára.
Ennek érdekében szeretnénk megtalálni a megfelelő szöget 2-2 fázistoló-lemez, és 3-3 MPC (Motorized Polarization Controller) számára,
hogy maximalizáljuk a két távoli pont közötti visibilityt.

Ennek érdekében két csomag kód készült, egy C++ nyelven, egy pedig Python nyelven,
a C++ feladata hogy a fázistoló-lemezeket forgassa, a Python kód feladata pedig az MPC, de később bővitve lett a Fázistoló lemezekkel is.

## C++

A cpp almappában található ez a része a projektnek, és a feladata elvégzéséhez több osztály is készült, más más részfeladatok elvégzéséhez.
Egy elméletben egyszerű módszerrel akarjuk optimalizálni a fázistoló-lemezek állását, azt csinálja a kód hogy kiválaszt egy fázistoló-lemezt,
azt egy teljes 180°-os fázison keresztül forgatja 10°-onként, és megnézi a rendszer állapotát,
majd a legjobb állapot körül egy ± 10°-os (lehet nem pont 10) tartományban kisebb lépésekben megkeresi a legjobb állapot, majd megy tovább a következő lemezre.
Ennek a működésnek a megvalósítása viszont nem triviális, és sok eszköz használatát kell megvalósítani hozzá illetve más részfeladatokat is meg kell oldani.
Ezek az alábbiak:

- kezelni kell a fázistoló-lemezeket, ezt a kinesis mappában lévő KinesisUtil osztály oldja meg
- kezelni kell a GPS órát, ezt az fs740 mappában lévő fs_util osztály oldja meg
- meg kell tudni találni a két állomás közötti késleltetést, ezt a Correlator mappában lévő Correlator oldja meg
- fenn kell tartani a két távoli állomás között egy TCP kapcsolatot, ezt a data_collection mappában lévő tcp_server és tcp_client kódok oédják meg
- ki kell tudni olvasni az adatokat, ezt a data_collection mappában lévő timestamps_acquisition... kódok oldják meg
- kell egy osztály ami vezérli az eszközöket, és elemzi az adatokat, ezt az orchestrator mappában lévő orchestrator osztály oldja

A kód használatához az első lépés felépíteni a tcp kapcsolatot a két állomás között, ehhez először a TCP kapcsolatot kell felépíteni,
először a szervert, utána pedig a klienst (alapesetben az orchestrator kezeli a parancsokat, de elérhető egy manuális mód is a -m vagy --manual használatával),
ekkor felépül a kapcsolat, és dolgozni kezd a rendszer az optimalizáláson. A lemez optimalizálása egy ciklus szerint történik,
ami először az egyik lemez egy teljes 180°-os fázisán elemzi a rendszer állapotát 10-esével, majd a megtalált optimum környezetét nézi.
A forgatást egy adatgyűjtéssel szinkronizálja a kód, amihez a GPS órára van szükség.
Majd a begyűjtött adatokon megkeresi a maximális visibility pontját és az idő alapján visszafejti a szöget.

~2026 február óta nem dolgoztam ezen a kódcsomagon, hanem én is a Python kódot kezdtem fejleszteni.

## Python

Ez a kódcsomag a python almappában található és sokkal több funkciót ölel magába, ezen kívűl aki készítette a nagy részét már nincs itt hogy leírja a kód ezen részét szóval nem biztos hogy tökeletes lesz a leírás.
Ez a kódcsomag egy GUI-val rendelkező TCP kliens-szerver felépítésű rendszert valósít meg,
magába foglalja az alábbi funkciókat:

- késleltetés meghatározása a két állomás között élő adatokkal

*MEGJEGYZÉS Sajnos ez a funkció sokszor nem ad helyes adatokat, mivel minden egyes mérés indításakor egy számára random offset lesz a két oldal közti timestampek közt. Ezt az offsetet sajnos élőben és csatornánként külön-külön kell meghatározni, mivel a következő mérésen megint új offset lesz. A kódban erre többféle ötlet és kód is van rá, de sajnos még egyik sem elég robosztus, ahhoz hogy élőben működjön.
MEGJEGYZÉS VÉGE*

- forgatása és optimális beállítása az MPCk-nek (a beütésszám maximalizálása)
- forgatása a fázislemezeknak (ez a rész teszteletlen, viszont egy jó péda arra, hogy hogyan lehet pythonban használni az eszközt)
- késleltetés meghatározása a két állomás között korábban gyűjtött adatokon (ennek a működése a c++ correlator alapján készült)
- koincidenciák kirajzolása nem élő adatokon

A programnak szüksége van a Thorlabs Kinesis dll-ekre, hogy az eszközöket tudja mozgatni, melyeket alapvetően itt keres: "C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.dllNeve.dll"
Ezeket innen töltöttük le: https://www.thorlabs.com/software-pages/motion_control/

A program használatához pythonnal futtasuk a main_guit.py -t, melyet először a Wigner állámáson índítsunk, mint szerver (mivel itt rendelkezünk publikus IP címmel/port forwarddal), majd ehhez csatlakoztassuk a BME-s oldalt, mint kliens. Minkét oldalon a kód ugyanannak a vezióját érdemes futtatni.
A GUI-n keresztül el lehet érni minden releváns funkciót egyszerű kattintásokkal, illetve a (gui_components/)config.py-ban állítható rengeteg szám ami a GUI-n belül nem.
A program elindítható magában is csak 1 vagy akár TimeControllerhez való csatlakozás nélkült, viszont ekkor a nem csatlakoztatott tc-hez csak mockolt adatot fog adni, melyre egy figyelmeztetést is mutat.