Az alábbi projekt azért készül, hogy előkészítse az optikai eszközöket egy Bell-teszt számára. 
Ennek érdekében szeretnénk megtalálni a megfelelő szöget 2-2 fázistoló-lemez, és 3-3 MPC (Motorized Polarization Controller) számára, 
hogy maximalizáljuk a két távoli pont közötti visibilityt. 

Ennek érdekében két csomag kód készült, egy C++ nyelven, egy pedig Python nyelven, 
a C++ feladata hogy a fázistoló-lemezeket forgassa, a Python kód feladata pedig az MPC, de később bővitve lett a Fázistoló lemezekkel is. 

C++
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


Python
    Ez a kódcsomag a python almappában található és sokkal több funkciót ölel magába, ezen kívűl aki készítette a nagy részét már nincs itt hogy leírja a kód ezen részét szóval nem biztos hogy tökeletes lesz a leírás.
    Ez a kódcsomag egy GUI-val rendelkező TCP kliens-szerver felépítésű rendszert valósít meg, 
    magába foglalja az alábbi funkciókat:
                                            - késleltetés meghatározása a két állomás között élő adatokkal
***MEGJEGYZÉS Sajnos ez a funkció sokszor nem ad helyes adatokat és nem tudtam rájönni miért, de valószínüleg az lehet a probléma hogy nincs eléggé szinkronban a két állomás működése, és valami 
ki random időeltolódás a rendszerben okozhat problémát. De az is lehetséges hogy maga a timetagger működése okozza ezt, mivel nincs olyan funkció benne ami 
élőben küldi az adatokat, ezért az "élő adatok" azt jelenti a gyakorlatban hogy adott méretű, ha jól emlékszem fél perces csomagokat küld a timetagger. 
Lehetséges hogy a folyamatos küldés egy olyan hálózati jittert okoz ami szintén problémát okozhat. De lehetséges más probléma is amire nem gondoltam. MEGJEGYZÉS VÉGE***

                                            - forgatása az MPCk-nek, később kiegészítve a fázislemezekkel (ezt a részt nem tudtam tesztelni, valószínüleg vannak benne hibák)
                                            - késleltetés meghatározása a két állomás között korábban gyűjtött adatokon (ennek a működése egy az egyben megegyezik a c++ correlator-ral)
                                            - koincidenciák kirajzolása nem élő adatokon

    A programot (main_gui.py) hasonlóan a másik verzióhoz úgy kell futatni hogy először a távoli állomáson kell elindítani szerver módban, majd a lokálison kliens módban.
    A GUI-n keresztül el lehet érni minden releváns funkciót egyszerű kattintásokkal, illetve a config.py-ban állítható rengeteg szám ami a GUI-n belül nem. 
            