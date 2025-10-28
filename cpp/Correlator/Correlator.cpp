#include "Correlator.h"

//fuggveny ami beolvassa a binaris adatfajlokat, feltolti a buff1, buff2 fftw komplex tomboket
//hisztogramot keszit a beolvasott adatokbol
size_t Correlator::read_data(const std::string& filePath, int buffId, uint64_t tau, size_t chunkSize, size_t N,
    size_t* hin, double* hout, size_t Nbin, size_t Tbin, uint64_t Tshift)
{
    std::ifstream inFile(filePath, std::ios::binary);
    if (!inFile) {
        std::perror("Error opening file");
        return 0;
    }

    size_t buffSize = 0, s = 0;
    std::vector<uint64_t> tmpBuff(chunkSize);

    // bufferek nullazasa
    for (size_t k = 0; k < N; ++k) {
        if (buffId == 1) {
            buff1[k][0] = 0.0;
            buff1[k][1] = 0.0;
        }
        else {
            buff2[k][0] = 0.0;
            buff2[k][1] = 0.0;
        }
    }

    std::fill(hin, hin + Nbin, 0);

    while (inFile.read(reinterpret_cast<char*>(tmpBuff.data()), chunkSize * sizeof(uint64_t))
        || inFile.gcount())
    {
        size_t numRead = inFile.gcount() / sizeof(uint64_t);
        buffSize += numRead;

        for (size_t k = 0; k + 1 < numRead; k += 2) {
            //azert ilyen formatumban vannak az adatok mert minden masodik adat a masodperc szamlalo
            //az elso adat pedig az masodperc ota eltelt idot
            uint64_t totalTime = (tmpBuff[k] + Tshift) + (tmpBuff[k + 1] * 1e12);
            size_t r = (size_t)(totalTime / tau) % N;
            if (buffId == 1) {
                buff1[r][0] += 1.0;
            }
            else {
                buff2[r][0] += 1.0;
            }
        }

        if (s == 0) {
            //adatok kiirasa ellenorzeskeppen
            print_uintvec("tmp_buff", tmpBuff.data(), std::min<size_t>(10, numRead));
        }

        histogram(tmpBuff.data(), numRead, hin, Nbin, Tbin);
        std::cerr << "dTmean[" << s++ << "] = " << dTmean(tmpBuff.data(), numRead) << ",\t";
    }

    hist_norm(hin, hout, Nbin);
    return buffSize;
}

//kiir egy uint64_t vectort a standard error kimenetre
void Correlator::print_uintvec(const char* name, uint64_t* v, size_t n)
{
    for (size_t k = 0; k < n; k++) {
        std::cerr << name << "[" << k << "] = " << v[k] << "\n";
    }
}

//kiszamolja egy double vectornak az atlagat
double Correlator::vec_mean(double* v, size_t n)
{
    double buff = 0;
    for (size_t k = 0; k < n; k++) {
        buff += v[k];
    }
    return buff / n;
}

//kiszamolja egy double vectornak a szorasat
double Correlator::vec_variance(double* v, double vmean, size_t n)
{
    double buff = 0;
    for (size_t k = 0; k < n; k++) {
        buff += (v[k] - vmean) * (v[k] - vmean);
    }
    return sqrt(buff / (n - 1));
}

//kiszamolja egy uint64_t vector atlagos kulonbseget
double Correlator::dTmean(uint64_t* v, size_t N)
{
    double dt = 0;
    for (size_t k = 1; k < N; ++k) {
        if (v[k] - v[k - 1] < 5e7)
            dt += v[k] - v[k - 1];
    }
    dt /= N - 1;
    return dt;
}

void Correlator::histogram(uint64_t* v, size_t N, size_t* h, size_t Nbin, size_t Tbin)
{
    for (size_t k = 1; k < N; ++k) {
        size_t r = (v[k] - v[k - 1]) / Tbin;
        if (r < Nbin) {
            h[r] += 1;
        }
    }
}

void Correlator::hist_norm(uint64_t* hin, double* hout, size_t Nbin) {
    double area = 0;
    for (size_t k = 0; k < Nbin; k++) {
        area += hin[k];
    }
    for (size_t k = 0; k < Nbin; k++) {
        hout[k] = hin[k] / area;
    }
}

//fourier transzformacioval kiszamolja a ket buffert korrelaciojat
//es visszater a korrelacio maximumaval es helyevel
Vmax Correlator::CalculateDeltaT(size_t N) {
    fftw_complex* buff1_c, * buff2_c;
    fftw_complex* cbuff, * cbuff_c;
    double* cbuffr, * S;
    double cmean, cvar;
    Vmax Smax;

    buff1_c = fftw_alloc_complex(N);
    buff2_c = fftw_alloc_complex(N);
    fftw_plan plan_forward1 = fftw_plan_dft_1d(N, buff1, buff1_c, FFTW_FORWARD, FFTW_ESTIMATE);
    fftw_plan plan_forward2 = fftw_plan_dft_1d(N, buff2, buff2_c, FFTW_FORWARD, FFTW_ESTIMATE);
    fftw_execute(plan_forward1);
    fftw_execute(plan_forward2);
    fftw_destroy_plan(plan_forward1);
    fftw_destroy_plan(plan_forward2);

    cbuff_c = fftw_alloc_complex(N);
    for (size_t k = 0; k < N; k++) {
        double real1 = buff1_c[k][0];
        double imag1 = buff1_c[k][1];
        double real2 = buff2_c[k][0];
        double imag2 = buff2_c[k][1];

        cbuff_c[k][0] = real1 * real2 + imag1 * imag2;
        cbuff_c[k][1] = -imag1 * real2 + real1 * imag2;
    }
    fftw_free(buff1_c);
    fftw_free(buff2_c);

    cbuff = fftw_alloc_complex(N);
    fftw_plan plan_backward = fftw_plan_dft_1d(N, cbuff_c, cbuff, FFTW_BACKWARD, FFTW_ESTIMATE);
    fftw_execute(plan_backward);
    fftw_destroy_plan(plan_backward);
    fftw_free(cbuff_c);

    cbuffr = new double[N];
    S = new double[N];
    for (size_t n = 0; n < N; n++) {
        cbuff[n][0] /= N;
        cbuff[n][1] /= N;
        cbuffr[n] = cbuff[n][0];
    }
    fftw_free(cbuff);

    cmean = vec_mean(cbuffr, N);
    cvar = vec_variance(cbuffr, cmean, N);

    std::cerr << "MEAN(cbuff) = " << cmean << ", VAR(cbuff) = " << cvar << "\n";

    for (size_t n = 0; n < N; ++n) {
        S[n] = (cbuffr[n] - cmean) / cvar;
        dataFile << S[n] << "\n";
    }

    Smax = rmax(S, N);
    delete[] cbuffr;
    delete[] S;
    return Smax;
}

//megkeresi egy double vector maximumat es helyet
Vmax Correlator::rmax(double* v, size_t N) {
    Vmax m;
    m.max = v[0];
    for (size_t k = 1; k < N; k++) {
        if (v[k] > m.max) {
            m.max = v[k];
            m.kmax = k;
        }
    }
    return m;
}

//megkeresi egy double vector minimumat es helyet
Vmin Correlator::rmin(double* v, size_t N) {
    Vmin m;
    m.min = v[0];
    for (size_t k = 1; k < N; k++) {
        if (v[k] < m.min) {
            m.min = v[k];
            m.kmin = k;
        }
    }
    return m;
}

//kiirja a hisztogramokat egy fajlba
void Correlator::print_hist(double* h1, double* h2, size_t Nbin) {
    for (size_t k = 1; k < Nbin; ++k) {
        dataFile << h1[k] << ", " << h2[k] << "\n";
    }
}

//kiir egy komplex vector a standard error kimenetre
void Correlator::print_cvec(char* name, std::complex<double>* v, size_t n)
{
    for (size_t k = 0; k < n; k++) {
        std::cerr << name << "[" << k << "] = "
            << real(v[k]) << "+" << imag(v[k]) << "i\n";
    }
}

//kiir egy double vector a standard error kimenetre
void Correlator::print_rvec(char* name, double* v, size_t n)
{
    for (size_t k = 0; k < n; k++) {
        std::cerr << name << "[" << k << "] = " << v[k] << "\n";
    }
}

//fajl meretet adja vissza byte-ban, azert kell mivel a zajszurest a nagyobb fajlra csinaljuk
size_t Correlator::get_file_size(const char* fname) {
    std::ifstream file(fname, std::ios::binary | std::ios::ate);
    if (!file) {
        std::perror("Error opening file");
        return 0;
    }
    return static_cast<size_t>(file.tellg());
}

//binaris keresessel megnezi hogy egy adott ertek benne van-e akarmelyik hatar kozott
bool Correlator::is_target_in_bound(Bound arr[], size_t size, uint64_t target) {
    size_t left = 0, right = size;
    while (left < right) {
        size_t mid = left + (right - left) / 2;
        if (arr[mid].upper > target)
            right = mid;
        else
            left = mid + 1;
    }
    return (left < size) && (arr[left].lower <= target && target <= arr[left].upper);
}

//a zajszurest altal megjelolt ertekeket torli a fajlbol
void Correlator::delete_marked_values(const char* fname) {
    std::cerr << "Deletion begins for marked values\n";

    std::ifstream inFile(fname, std::ios::binary);
    if (!inFile) {
        std::perror("Error opening input file");
        return;
    }

    std::ofstream tempFile("temp.bin", std::ios::binary);
    if (!tempFile) {
        std::perror("Error creating temporary file");
        return;
    }

    //eloszor atmesolja az adatokat egy ideiglenes fajlba, kihagyva a torlendo ertekeket
    std::vector<uint64_t> buffer(chunk_size);
    size_t chunkCnt = 0;
    while (inFile.read(reinterpret_cast<char*>(buffer.data()), buffer.size() * sizeof(uint64_t)) || inFile.gcount()) {
        size_t readCount = inFile.gcount() / sizeof(uint64_t);
        for (size_t i = 0; i < readCount; ++i) {
            //marked vector tartalmazza a torlendo ertekek indexeit (chunkCnt * chunk_size + i az index)
            if (!std::binary_search(marked.begin(), marked.end(), chunkCnt * chunk_size + i)) {
                tempFile.write(reinterpret_cast<char*>(&buffer[i]), sizeof(uint64_t));
            }
        }
        chunkCnt++;
    }
    inFile.close();
    tempFile.close();

    //majd visszairja az adatokat az eredeti fajlba
    std::ifstream tempIn("temp.bin", std::ios::binary);
    std::ofstream outFile(fname, std::ios::binary | std::ios::trunc);
    if (!tempIn || !outFile) {
        std::perror("Error reopening files");
        return;
    }

    outFile << tempIn.rdbuf();

    std::cerr << "Copying finished\n";
}

size_t Correlator::get_delay_estimate() {
    return 10000;
}

//zajszures azon az alapon hogy azokat az ertekeket torli a nagyobb fajlbol aminek nincs megfelelo parja a kisebb fajlban
void Correlator::noise_reduc_bound(const char* fp1, const char* fp2) {
    std::cerr << "noise reduc bound begin\n";
    size_t size1 = get_file_size(fp1);
    size_t size2 = get_file_size(fp2);
    std::cerr << "Size1: " << size1 << ", size2: " << size2 << "\n";

    const char* larger_fp_name = (size1 > size2) ? fp1 : fp2;
    const char* smaller_fp_name = (size1 < size2) ? fp1 : fp2;

    //nincs kulonosebb oka miert pont ennyi, eloszor ezt irtam be es mukodott azota nem valtoztattam rajta
    size_t bound_size = 10000;

    std::ifstream smallerFile(smaller_fp_name, std::ios::binary);
    if (!smallerFile) {
        std::perror("error opening smaller file");
        return;
    }

    size_t num_elements = ((size1 > size2) ? size1 : size2) / sizeof(uint64_t) / 2;
    size_t num_elements_smaller = ((size1 < size2) ? size1 : size2) / sizeof(uint64_t) / 2;

    std::vector<uint64_t> datapoints(chunk_size);
    std::vector<Bound> bounds(num_elements_smaller);
    size_t k = 0;
    size_t delay = get_delay_estimate();

    //elso korben meghatarozza a kisebb fajl minden egyes ertekere a hatarokat
    std::cerr << "Determining bounds\n";
    while (smallerFile.read(reinterpret_cast<char*>(datapoints.data()), datapoints.size() * sizeof(uint64_t)) || smallerFile.gcount()) {
        size_t readCount = smallerFile.gcount() / sizeof(uint64_t);
        for (size_t i = 0; i + 1 < readCount; i += 2) {
            uint64_t datapoint = datapoints[i] + (datapoints[i + 1] * static_cast<uint64_t>(1e12));
            bounds[k].lower = (datapoint > delay + bound_size) ? datapoint - delay - bound_size : 0;
            bounds[k++].upper = datapoint - delay + bound_size;
        }
    }
    smallerFile.close();

    std::fstream largerFile(larger_fp_name, std::ios::in | std::ios::out | std::ios::binary);
    if (!largerFile) {
        std::cerr << "Cannot open larger file\n";
        return;
    }

    //masodik korben megnezi hogy a nagyobb fajl minden egyes erteke benne van-e a kisebb fajl hatarai kozott
    //ami nem az bekerul a marked vectorba
    std::cerr << "Marking values outside of bounds\n";
    size_t chunkCnt = 0;
    marked.clear();
    while (largerFile.read(reinterpret_cast<char*>(datapoints.data()), datapoints.size() * sizeof(uint64_t)) || largerFile.gcount()) {
        size_t readCount = largerFile.gcount() / sizeof(uint64_t);
        for (size_t i = 0; i + 1 < readCount; i += 2) {
            uint64_t datapoint = datapoints[i] + (datapoints[i + 1] * static_cast<uint64_t>(1e12));
            if (!is_target_in_bound(bounds.data(), num_elements_smaller, datapoint)) {
                marked.push_back(chunkCnt * chunk_size + i);
                marked.push_back(chunkCnt * chunk_size + i + 1);
            }
        }
        ++chunkCnt;
    }
    largerFile.close();

    //rendezni kell hogy gyors legyen a kereses a delete_marked_values fuggvenyben
    //elmeletileg mar alapbol rendezve kellene lennie mivel sorban olvassa be a fajlt
    //de biztos ami biztos, plusz volt amikor nem mukodott enelkul, remelem nem egy masik hiba miatt
    std::sort(marked.begin(), marked.end());
    delete_marked_values(larger_fp_name);
}

//sok kicsi fajl osszefuzese egy nagyobb fajlba, mikozben minden ertekhez hozzad egy adott delay-t
//a delay az korabban tesztelesre kellett, a valosagban mar benne van az adatokban, de benne hagytam a fuggvenyben hatha kesobb is lesz teszteles
void Correlator::copyFiles(const std::vector<std::string>& inputPaths, const char* outputPath, size_t delay) {
    std::ofstream outputFile(outputPath, std::ios::binary | std::ios::trunc);
    if (!outputFile) {
        std::perror("Error opening output file");
        return;
    }

    std::vector<uint64_t> buffer(chunk_size);

    for (const auto& inputPath : inputPaths) {
        std::ifstream inputFile(inputPath, std::ios::binary);
        if (!inputFile) {
            std::cerr << "Error opening input file " << inputPath << "\n";
            continue; // skip this file
        }

        while (inputFile.read(reinterpret_cast<char*>(buffer.data()), buffer.size() * sizeof(uint64_t))
            || inputFile.gcount()) {
            size_t readCount = inputFile.gcount() / sizeof(uint64_t);
            for (size_t i = 0; i < readCount; ++i) {
                buffer[i] += delay;
            }
            outputFile.write(reinterpret_cast<char*>(buffer.data()), readCount * sizeof(uint64_t));
        }
    }
}

//korrelacio futtatasa
uint64_t Correlator::runCorrelation(bool reducStr, const std::vector<std::string>& dataset1Path, const std::vector<std::string>& dataset2Path, uint64_t tauInput)
{
    time_t t0 = time(NULL);

    this->tau = tauInput;

    //azert kell mert tobb fajlbol all a bemenet, illetve nem akarunk torolni az eredeti adatokbol
    copyFiles(dataset1Path, this->modifiable_dataset1, 0);
    copyFiles(dataset2Path, this->modifiable_dataset2, 0);

    //zajszures ha kell
    if (reducStr) {
        noise_reduc_bound(this->modifiable_dataset1, this->modifiable_dataset2);
    }

    this->buff1 = fftw_alloc_complex(this->N);
    this->buff2 = fftw_alloc_complex(this->N);
    if (!this->buff1 || !this->buff2) {
        fprintf(stderr, "FFTW alloc failed\n");
        if (this->buff1) fftw_free(this->buff1);
        if (this->buff2) fftw_free(this->buff2);
        return EXIT_FAILURE;
    }

    std::string dataset1 = this->modifiable_dataset1;
    this->buff1_size = read_data(dataset1, 1,
        this->tau,
        this->chunk_size,
        this->N,
        this->h1,
        this->h1d,
        Nbin,
        this->Tbin,
        this->Tshift);

    std::string dataset2 = this->modifiable_dataset2;
    this->buff2_size = read_data(dataset2, 2,
        this->tau,
        this->chunk_size,
        this->N,
        this->h2,
        this->h2d,
        Nbin,
        this->Tbin,
        /*Tshift=*/0);

    Vmax smax = CalculateDeltaT(this->N);
    fprintf(stderr, "max(S) = %f, kmax = %zu\n", smax.max, smax.kmax);
    fprintf(stderr, "Delta T = %" PRIu64 "\n", this->tau * (uint64_t)smax.kmax);

    fftw_free(this->buff1);
    fftw_free(this->buff2);
    this->buff1 = nullptr;
    this->buff2 = nullptr;

    fprintf(stderr, "Futasi ido: %ld\n", (long)(time(NULL) - t0));
    return this->tau * (uint64_t)smax.kmax;
}
