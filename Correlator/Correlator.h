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
const uint64_t MARKED_FOR_DELETION = 0xFFFFFFFFFFFFFFFF;

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
private:
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
    const char* modifialbe_dataset1 = "ts1.bin";
    const char* modifialbe_dataset2 = "ts2.bin";

public:
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

    ~Correlator() {
        if (dataFile.is_open()) {
            dataFile.close();
        }
    }

    size_t read_data(const std::string&, int, uint64_t, size_t, size_t, size_t*, double*, size_t, size_t, uint64_t);
    void print_uintvec(const char*, uint64_t*, size_t);
    void print_cvec(char*, std::complex<double>*, size_t);
    void print_rvec(char*, double*, size_t);
    double vec_mean(double*, size_t);
    double vec_variance(double*, double, size_t);
    double dTmean(uint64_t*, size_t);
    void histogram(uint64_t*, size_t, size_t*, size_t, size_t);
    void hist_norm(uint64_t*, double*, size_t);
    Vmax CalculateDeltaT(size_t);
    Vmax rmax(double*, size_t);
    Vmin rmin(double*, size_t);
    void print_hist(double*, double*, size_t);
    size_t get_file_size(const char*);
    bool is_target_in_bound(Bound[], size_t, uint64_t);
    void delete_marked_values(const char*);
    size_t get_delay_estimate();
    void noise_reduc_bound(const char*, const char*);
    void copyFiles(const std::vector<std::string>&, const char*, size_t);
    int runCorrelation(bool, const std::vector<std::string>&, const std::vector<std::string>&, uint64_t);
    std::vector<int> marked;
};
