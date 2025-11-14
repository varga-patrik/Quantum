#pragma once

#include "Winsock2.h"
#include "ws2tcpip.h"
#include <stdio.h>
#include <string>
#include <iostream>
#include <ctime>
#include <chrono>
#include <thread>
#include <iomanip>
#include <fstream>
#include <sstream>

class FSUtil{
    private:

    SOCKET sFS740;
    unsigned fs740_timeout;
    unsigned long ip;
    char buffer[1024];
    std::string ip_text;
    std::string output_file;
    bool connected;

    public:

    FSUtil(unsigned timeout, std::string ip_str, std::string output){
        fs740_timeout = timeout;
        init_tcpip();
        ip_text = ip_str;
        inet_pton(AF_INET, ip_text.c_str(), &ip);
        output_file = output;
        if(fs740_connect(ip)){
            std::cout << "Connection Succeeded" << std::endl;
            connected = true;
        }
        else{
            connected = false;
        }
    }
    ~FSUtil(){
        fs740_write("*opc?\n");
        if ( !fs740_read(buffer,sizeof(buffer)) )
            printf("Timeout\n");
                
        if (fs740_close())
            printf("Closed connection to FS740\n");
        else
            printf("Unable to close connection");
    }
    void run(std::string path); //futtatja a fájlt aminek a helyét a path adja, .exe és .py-ra képes helyes config esetén
    bool is_same_str(const char* str1, const char* str2); //két string megegyezik-e 
    void init_tcpip(void);
    int fs740_connect(unsigned long ip);
    int fs740_close(void);
    int fs740_write(const char *str);
    int fs740_write_bytes(const void *data, unsigned num);
    int fs740_read(char *buffer, unsigned num);
    std::string precise_computer_time(); //stringként megadja az időt a gépen abban a formátumban amiben a gps is megadja
    int64_t calculate_time_diff(const char *buff1, const char* buff2); //kiszámolja az időkülönbséget két időpont között picosecben
    void write_diff_to_file(double delta, const std::string& filename); //kiírja fájlba a megadott számot, csak akkor működik ha admin jogokkal fut az .exe
    void wait_until(const char* t); //vár egy időpontig, addig nem engedi a thread-et, gps órát használ, nem pedig thread::sleep_for-t
    bool is_earlier_time(const char* t1, const char* t2); //megmondja hogy a két időpont közül az egyik korábbi e
    void scpi_terminal(); //terminál amin keresztül lehet kommunikálni az fs-sel, exit command zárja be
    std::string start_time(); //string ami megadja azt az időt amig varni fog mérés előtt
    void measure_setup(); //előkészítni a mérést
    void measure_timedrift(int steps);
    std::string print_gpstime();
    bool is_in(const char* str, const char* substr);
};