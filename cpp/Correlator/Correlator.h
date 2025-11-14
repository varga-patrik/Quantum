#pragma once

#include <cstdint>
#include <fftw3.h>
#include <inttypes.h>
#include <cstdio>
#include <fstream>
#include <vector>
#include <complex>
#include <cmath>
#include <iostream>
#include <algorithm>

const size_t Nbin = 200;

typedef struct Vmax
{
    double max;
    size_t kmax;
} Vmax;
typedef struct Vmin
{
    double min;
    size_t kmin;
} Vmin;
typedef struct Bound {
    uint64_t lower;
    uint64_t upper;
} Bound;

class Correlator
{
public:
    std::ofstream dataFile;
    const size_t chunk_size;
    fftw_complex* buff1, * buff2;
    uint64_t N;
    size_t buff1_size, buff2_size;
    Vmax Smax, best;
    uint64_t tau;
    uint64_t Tshift;
    size_t Tbin;
    size_t h1[Nbin];
    size_t h2[Nbin];
    double h1d[Nbin];
    double h2d[Nbin];
    const char* dataset1;
    const char* dataset2;
    const char* modifiable_dataset1 = "ts1.bin";
    const char* modifiable_dataset2 = "ts2.bin";
    std::vector<int> marked; //torlendo ertekek indexei


    Correlator(size_t chunkSize, uint64_t Nval)
        :dataFile("a.dat"),
        chunk_size(chunkSize),
        buff1(nullptr),
        buff2(nullptr),
        N(Nval),
        buff1_size(0),
        buff2_size(0),
        tau(0),
        Tshift(100000000),   // alap�rtelmezett shift
        Tbin(1000),          // alap�rtelmezett bin
        dataset1(nullptr),
        dataset2(nullptr)
    {
        // hisztogram t�mb�k null�z�sa
        std::fill_n(h1, Nbin, 0);
        std::fill_n(h2, Nbin, 0);
        std::fill_n(h1d, Nbin, 0.0);
        std::fill_n(h2d, Nbin, 0.0);
        if (!dataFile.is_open()) {
            std::cerr << "Error: could not open a.dat for writing\n";
        }
        Smax.max = 0.0;
        Smax.kmax = 0;
        best.max = 0.0;
        best.kmax = 0;
    }

    Correlator(const Correlator& other)
        : dataFile("a.dat"),
        chunk_size(other.chunk_size),
        buff1(nullptr),
        buff2(nullptr),
        N(other.N),
        buff1_size(other.buff1_size),
        buff2_size(other.buff2_size),
        tau(other.tau),
        Tshift(other.Tshift),
        Tbin(other.Tbin),
        dataset1(nullptr),
        dataset2(nullptr)
    {
        // Copy histograms
        std::copy(other.h1,  other.h1  + Nbin, h1);
        std::copy(other.h2,  other.h2  + Nbin, h2);
        std::copy(other.h1d, other.h1d + Nbin, h1d);
        std::copy(other.h2d, other.h2d + Nbin, h2d);

        // Report file error if needed
        if (!dataFile.is_open()) {
            std::cerr << "Error: could not open a.dat for writing\n";
        }

        // Copy Smax and best structures
        Smax = other.Smax;
        best = other.best;
    }

    ~Correlator() {
        if (dataFile.is_open()) {
            dataFile.close();
        }
    }

    size_t read_data(const std::string&, int, uint64_t, size_t, size_t, size_t*, double*, size_t, size_t, uint64_t); //adatok beolvasasa es feldolgozasa
    void print_uintvec(const char*, uint64_t*, size_t); //kiir egy uint64_t vectort a standard error kimenetre
    void print_cvec(char*, std::complex<double>*, size_t); //kiir egy komplex vector a standard error kimenetre
    void print_rvec(char*, double*, size_t); //kiir egy double vector a standard error kimenetre
    double vec_mean(double*, size_t); //kiszamolja egy double vectornak az atlagat
    double vec_variance(double*, double, size_t); //kiszamolja egy double vectornak a szorasat
    double dTmean(uint64_t*, size_t); //kiszamolja egy uint64_t vector atlagos kulonbseget
    void histogram(uint64_t*, size_t, size_t*, size_t, size_t); //hisztogram keszites
    void hist_norm(uint64_t*, double*, size_t); //hisztogram normalizalas
    Vmax CalculateDeltaT(size_t); //maximalis korrelacio es helye
    Vmax rmax(double*, size_t); //megkeresi egy double vector maximumat es helyet
    Vmin rmin(double*, size_t); //megkeresi egy double vector minimumat es helyet
    void print_hist(double*, double*, size_t); //kiirja a hisztogramokat egy fajlba
    size_t get_file_size(const char*); //fajl meretenek lekerdezese
    bool is_target_in_bound(Bound[], size_t, uint64_t); //binaris keresessel megnezi hogy egy adott ertek benne van-e akarmelyik hatar kozott
    void delete_marked_values(const char*); //torli a megjelolt ertekeket egy fajlbol
    size_t get_delay_estimate(); //visszaad egy becsult delay erteket, ez attol fugg hogy a valosagban mit becslunk kesleltetesnek a ket allomas kozott
    void noise_reduc_bound(const char*, const char*); //zajszures
    void copyFiles(const std::vector<std::string>&, const char*, size_t); //sok kicsi fajl osszefuzese egy nagyobb fajlba, mikozben minden ertekhez hozzad egy adott delay-t
    uint64_t runCorrelation(bool, const std::vector<std::string>&, const std::vector<std::string>&, uint64_t); //korrelacio futtatasa
};
