//forrás: https://learn.microsoft.com/en-us/windows/win32/winsock/complete-client-code
//ez a link tartalmazza a kliens skeletont, amit felhasznaltam

#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <stdlib.h>
#include <stdio.h>
#include <iostream>
#include <filesystem>
#include <sstream>
#include "fs740/fs_util.h"
#include "kinesis/KinesisUtil.h"
#include "Correlator/Correlator.h"
#include "direct.h"

#pragma comment (lib, "Ws2_32.lib")
#pragma comment (lib, "Mswsock.lib")
#pragma comment (lib, "AdvApi32.lib")


#define DEFAULT_BUFLEN 512
#define DEFAULT_PORT "27015"

std::vector<std::string> uploadFiles(const std::string& folder, const std::string& condition) {
    std::vector<std::string> files;

    try {
        for (const auto& entry : std::filesystem::directory_iterator(folder)) {
            if (!entry.is_regular_file()) continue; 
            std::string filename = entry.path().filename().string();

            if (filename.find(condition) != std::string::npos) {
                files.push_back(entry.path().string());
            }
        }
    }
    catch (const std::filesystem::filesystem_error& e) {
        std::cerr << "Filesystem error: " << e.what() << std::endl;
    }

    return files;
}

int main(int argc, char **argv) 
{
    WSADATA wsaData;
    SOCKET ConnectSocket = INVALID_SOCKET;
    struct addrinfo *result = NULL,
                    *ptr = NULL,
                    hints;
    std::string sendbuf;
    char recvbuf[DEFAULT_BUFLEN];
    int iResult;
    int recvbuflen = DEFAULT_BUFLEN;

    //kapcsolat felepitese a gps oraval, output stringhez nem tartozik erdemi funkcio, azt korabban tesztelesre hasznaltam
    std::string ip_text = "148.6.27.165";
    std::string output = "diff_data.csv";
    FSUtil fs(6000, ip_text, output);

    char pathbuffer[1024];
    getcwd(pathbuffer, 1024);
    
    // Validate the parameters
    if (argc != 2) {
        printf("usage: %s server-name\n", argv[0]);
        return 1;
    }

    // Initialize Winsock
    iResult = WSAStartup(MAKEWORD(2,2), &wsaData);
    if (iResult != 0) {
        printf("WSAStartup failed with error: %d\n", iResult);
        return 1;
    }

    ZeroMemory( &hints, sizeof(hints) );
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    // Resolve the server address and port
    iResult = getaddrinfo(argv[1], DEFAULT_PORT, &hints, &result);
    if ( iResult != 0 ) {
        printf("getaddrinfo failed with error: %d\n", iResult);
        WSACleanup();
        return 1;
    }

    // Attempt to connect to an address until one succeeds
    for(ptr=result; ptr != NULL ;ptr=ptr->ai_next) {

        // Create a SOCKET for connecting to server
        ConnectSocket = socket(ptr->ai_family, ptr->ai_socktype, 
            ptr->ai_protocol);
        if (ConnectSocket == INVALID_SOCKET) {
            printf("socket failed with error: %ld\n", WSAGetLastError());
            WSACleanup();
            return 1;
        }

        // Connect to server.
        iResult = connect( ConnectSocket, ptr->ai_addr, (int)ptr->ai_addrlen);
        if (iResult == SOCKET_ERROR) {
            closesocket(ConnectSocket);
            ConnectSocket = INVALID_SOCKET;
            continue;
        }
        break;
    }

    freeaddrinfo(result);

    if (ConnectSocket == INVALID_SOCKET) {
        printf("Unable to connect to server!\n");
        WSACleanup();
        return 1;
    }

    std::cout << "Connected to server" << std::endl;
    
    //ebben a while blokkban tortenik minden relevans funkcio
    //--------------------------------------------------------
    //fontos, hogy amikor teszteles keppen egy geprol, de ket kulonbozo terminalon futtatod a server es a client programot,
    //akkor valamelyik oldalon ki kell kommentelni a parancsok lefuttatasat, mivel mindket eszkoz ugyanazokkal a muszerekkel kommunikalna
    //nem tudom pontosan mekkora lenne a kar, valoszinuleg csak egy error az egyik oldalon, de ezek a muszerek eleg dragak, nem kockaztatnam
    //--------------------------------------------------------

    KinesisUtil device_bme_4("12345679");
    KinesisUtil device_bme_2("12345679");

    device_bme_2.home();
    device_bme_4.home();

    Correlator correlator(100000, (1ULL << 16));

    double rotation_stages[19] = { 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90 };
    int counter_bme_4 = 0;
    int counter_bme_2 = 0;

    std::vector<uint64_t> results;

    while(!fs.is_same_str(sendbuf.c_str(), "exit")){
        std::ostringstream path;
        std::cout << "Type here: ";
        std::cin >> sendbuf; 

        //setup parancs elokesziti a muszereket a meresre
        if(fs.is_same_str(sendbuf.c_str(), "setup")){
            fs.measure_setup();
            path.clear();
            path << "\"" << pathbuffer << "\\timetagger_setup.py\"";
            fs.run(path.str());
        }

        //meg a start futtatasa elott a kliens kituzi a meres idejet es igy kuldi el ezt a masik oldalnak
        if(fs.is_same_str(sendbuf.c_str(), "start")){
            sendbuf += " ";
            sendbuf += fs.start_time();
        }

        if(fs.is_same_str(sendbuf.c_str(), "activate bme")){
            device_bme_2.activate();
            device_bme_4.activate();
        }

        if(fs.is_same_str(sendbuf.c_str(), "deactivate bme")){
            device_bme_2.deactivate();
            device_bme_4.deactivate();
        }

        if (fs.is_same_str(sendbuf.c_str(), "rotate")) {
            if (counter_bme_2 == 18) {

                std::vector<std::string> dataset1 = uploadFiles("./data", "bme");
                std::vector<std::string> dataset2 = uploadFiles("./data", "wigner");
                results.push_back(correlator.runCorrelation(true, dataset1, dataset2, 500));

                if (!device_bme_4.moveToPosition(rotation_stages[counter_bme_4])) {
                    std::cout << "ERROR with bme 4" << std::endl;
                }

                if (!device_bme_2.moveToPosition(rotation_stages[counter_bme_2])) {
                    std::cout << "ERROR with bme 2" << std::endl;
                }
                counter_bme_2 = 0;
                counter_bme_4++;
            }
            else {

                std::vector<std::string> dataset1 = uploadFiles("./data", "bme");
                std::vector<std::string> dataset2 = uploadFiles("./data", "wigner");
                results.push_back(correlator.runCorrelation(true, dataset1, dataset2, 500));

                if (!device_bme_4.moveToPosition(rotation_stages[counter_bme_4])) {
                    std::cout << "ERROR with bme 4" << std::endl;
                }

                if (!device_bme_2.moveToPosition(rotation_stages[counter_bme_2])) {
                    std::cout << "ERROR with bme 2" << std::endl;
                }

                counter_bme_2++;
            }

            std::cout<< "Current position: "<< std::endl << "BME4: " << rotation_stages[counter_bme_4] 
                << std::endl << "Wigner2: " << rotation_stages[counter_bme_2] << std::endl; 
        }

        iResult = send( ConnectSocket, sendbuf.c_str(), DEFAULT_BUFLEN, 0 );

        if (iResult == SOCKET_ERROR) {
            printf("send failed with error: %d\n", WSAGetLastError());
            closesocket(ConnectSocket);
            WSACleanup();
            return 1;
        }

        //ez a meres, a program megvarja a kezdes idopontjat es lefuttatja a merest
        else if(sendbuf.find("start")!=std::string::npos){
            fs.wait_until(sendbuf.substr(6).c_str());
            path.clear();
            path << "\"" << pathbuffer << "\\timestamps_acquisition.py\"";
            fs.run(path.str());
        }
    }

    uint64_t maxValue = 0;
    size_t maxIndex = 0;

    for (size_t i = 0; i < results.size(); i++) {
        if (results[i] > maxValue) {
            maxValue = results[i];
            maxIndex = i;
        }
    }

    // reconstruct which angles correspond to this measurement
    int totalStages = 19;
    int hwpIndex = static_cast<int>(maxIndex / totalStages);
    int qwpIndex = static_cast<int>(maxIndex % totalStages);

    double bestHwpAngle = rotation_stages[hwpIndex];
    double bestQwpAngle = rotation_stages[qwpIndex];

    std::cout << "\n=== BEST RESULT ===" << std::endl;
    std::cout << "Max correlation value: " << maxValue << std::endl;
    std::cout << "Wigner 4 angle: " << bestHwpAngle << " degrees" << std::endl;
    std::cout << "Wigner 2 angle: " << bestQwpAngle << " degrees" << std::endl;

    // shutdown the connection since no more data will be sent
    iResult = shutdown(ConnectSocket, SD_SEND);
    if (iResult == SOCKET_ERROR) {
        printf("shutdown failed with error: %d\n", WSAGetLastError());
        closesocket(ConnectSocket);
        WSACleanup();
        return 1;
    }

    // Receive until the peer closes the connection
    do {
        iResult = recv(ConnectSocket, recvbuf, recvbuflen, 0);
        if ( iResult > 0 )
            printf("Bytes received: %d\n", iResult);
        else if ( iResult == 0 )
            printf("Connection closed\n");
        else
            printf("recv failed with error: %d\n", WSAGetLastError());

    } while( iResult > 0 );

    // cleanup
    closesocket(ConnectSocket);
    WSACleanup();

    return 0;
}