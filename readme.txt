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
            

**ENGLISH**

This project was created to prepare the optical devices for a Bell test.

To achieve this, we aim to find the appropriate angles for two wave plates and three Motorized Polarization Controllers (MPCs) on each side in order to maximize the visibility between two remote stations.

To support this goal, two software packages were developed: one in C++ and one in Python. The C++ package is responsible for controlling the wave plates, while the Python package was originally developed for the MPCs but was later extended to support the wave plates as well.

## C++

The C++ portion of the project is located in the `cpp` directory. To accomplish its task, several classes were developed, each handling a specific subsystem.

The wave plate optimization follows a conceptually simple strategy. The software selects a wave plate and rotates it through its full 180° range in 10° increments while evaluating the state of the system. Once the best region is identified, the software performs a finer search within a range around the optimum (typically approximately ±10°) using smaller step sizes. After finding the optimal position, it proceeds to the next wave plate.

Implementing this process is not trivial, as it requires controlling multiple devices and solving several supporting tasks. These include:

* Controlling the wave plates, implemented by the `KinesisUtil` class located in the `kinesis` directory.
* Communicating with the GPS clock, implemented by the `fs_util` class located in the `fs740` directory.
* Determining the delay between the two stations, implemented by the `Correlator` class located in the `Correlator` directory.
* Maintaining a TCP connection between the two remote stations, implemented by the `tcp_server` and `tcp_client` components located in the `data_collection` directory.
* Acquiring timestamp data, implemented by the `timestamps_acquisition` components located in the `data_collection` directory.
* Coordinating all devices and analyzing the collected data, implemented by the `Orchestrator` class located in the `orchestrator` directory.

To use the software, the first step is to establish a TCP connection between the two stations. This is done by starting the server first and then the client. Under normal operation, the `Orchestrator` handles all commands automatically, although a manual mode is also available using the `-m` or `--manual` command-line options.

Once the connection has been established, the system begins the optimization process. The optimization follows an iterative cycle in which a wave plate is rotated through its full 180° range in 10° steps while the system state is continuously evaluated. After identifying the most promising region, a finer search is performed around the optimum.

The rotation process is synchronized with data acquisition using the GPS clock. After the data has been collected, the software searches for the point of maximum visibility and determines the corresponding wave plate angle by analyzing the timing information.

I have not actively worked on this codebase since approximately February 2026, as I later shifted my focus to developing the Python version.

## Python

This software package is located in the `python` directory and provides significantly more functionality.

Additionally, the original developer responsible for most of this code is no longer available, so this description may not be entirely complete or accurate.

The Python package implements a GUI-based client-server system and provides the following functionality:

* Determination of the delay between the two stations using live data.

**NOTE:** Unfortunately, this feature often produces incorrect results, and I was unable to determine the exact cause. My best guess is that the two stations are not sufficiently synchronized and that some random timing offset within the system is causing the issue.

It is also possible that the problem originates from the Time Tagger itself. The device does not provide a true real-time streaming mode, so "live data" in practice consists of data packets of fixed duration, which, if I remember correctly, are approximately 30 seconds long.

It is possible that continuous packet transmission introduces network jitter that affects the delay calculation. However, there may also be other causes that I have not identified.

**END OF NOTE**

* Control of the MPCs, later extended to include wave plate control as well. I was unable to test this functionality thoroughly, so it likely contains bugs.
* Determination of the delay between the two stations using previously recorded data. This functionality is effectively identical to the C++ `Correlator`.
* Visualization of coincidence measurements using recorded data.

The program (`main_gui.py`) is started similarly to the C++ version. The server should first be started on the remote station, followed by the client on the local station.

All relevant functionality is accessible through the graphical user interface via simple button clicks. Additionally, many configuration parameters that are not exposed through the GUI can be adjusted directly in the `config.py` file.
