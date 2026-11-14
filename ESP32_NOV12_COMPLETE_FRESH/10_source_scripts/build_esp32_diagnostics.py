from pathlib import Path
src=Path('/mnt/data/esp32_benchmark_logged.ino').read_text()
def rep(a,b):
 global src
 n=src.count(a)
 if n!=1: raise RuntimeError(f'expected once ({n}): {a[:90]!r}')
 src=src.replace(a,b,1)
rep('#define PIN_SPI_MISO 27','#define PIN_SPI_MISO 27\n#define PIN_DIAG 26   // GPIO26 = optional extra marker (NOT DAC CH1 in these tests)')
rep('#define PIN25_LOW()       REG_WRITE(GPIO_OUT_W1TC_REG, (1UL << PIN_DMA))','#define PIN25_LOW()       REG_WRITE(GPIO_OUT_W1TC_REG, (1UL << PIN_DMA))\n#define DIAG_HIGH()        REG_WRITE(GPIO_OUT_W1TS_REG, (1UL << PIN_DIAG))\n#define DIAG_LOW()         REG_WRITE(GPIO_OUT_W1TC_REG, (1UL << PIN_DIAG))')
rep('volatile CacheMissMode active_cache_mode = CACHE_MISS_0_PCT;', '''volatile CacheMissMode active_cache_mode = CACHE_MISS_0_PCT;
// Diagnostic feature flags: F toggles flush without changing access pattern.
volatile bool diag_do_cache_flush = true;
volatile uint32_t diag_isr_count = 0;
// Only dispatcher writes these; read after sw_timer_callback returns.
uint32_t diag_last_flush = 0, diag_last_callback = 0;
uint32_t diag_last_load_isrs = 0, diag_last_flush_isrs = 0;
uint32_t diag_last_ring_depth = 0;''')
rep('DRAM_ATTR static uint32_t __attribute__((aligned(32))) bench_entry_samples[BENCH_MAX_SAMPLES];','''DRAM_ATTR static uint32_t __attribute__((aligned(32))) bench_entry_samples[BENCH_MAX_SAMPLES];
DRAM_ATTR static uint32_t diag_flush_samples[BENCH_MAX_SAMPLES];
DRAM_ATTR static uint32_t diag_callback_samples[BENCH_MAX_SAMPLES];
DRAM_ATTR static uint32_t diag_load_isr_samples[BENCH_MAX_SAMPLES];
DRAM_ATTR static uint32_t diag_flush_isr_samples[BENCH_MAX_SAMPLES];
DRAM_ATTR static uint32_t diag_ringdepth_samples[BENCH_MAX_SAMPLES];''')
rep('volatile uint32_t spi_cb_count = 0;', '''volatile uint32_t spi_cb_count = 0;
volatile uint32_t diag_spi_pre_cycles = 0;
volatile uint32_t diag_spi_pre_count = 0;
volatile uint32_t diag_dac_stalls = 0, diag_dac_steps = 0, diag_dac_write_calls = 0;
volatile uint64_t diag_dac_write_ccount_total = 0;
volatile uint32_t diag_dac_write_ccount_max = 0;''')
# cache marker spans flush and measured loads, lower before LUT
rep('''    if (mode != CACHE_MISS_0_PCT) {
        hw_invalidate_pro_cache();
    }

    const uint32_t work_start = bench_read_ccount();
    MARKER_HIGH();''','''    const uint32_t whole_start = bench_read_ccount();
    DIAG_HIGH(); // A8 if attached; full cache callback (flush + work + LUT).
    const uint32_t flush_before = diag_isr_count;
    const uint32_t flush_start = bench_read_ccount();
    if (mode != CACHE_MISS_0_PCT && diag_do_cache_flush) {
        hw_invalidate_pro_cache();
    }
    diag_last_flush = bench_read_ccount() - flush_start;
    diag_last_flush_isrs = diag_isr_count - flush_before;

    const uint32_t work_start = bench_read_ccount();
    const uint32_t load_before = diag_isr_count;
    MARKER_HIGH();''')
rep('''    const uint32_t work_width = bench_read_ccount() - work_start;

    cb_flash_cursor''','''    const uint32_t work_width = bench_read_ccount() - work_start;
    diag_last_load_isrs = diag_isr_count - load_before;

    cb_flash_cursor''')
rep('''    cb_count = c + 1U;
    return work_width;''','''    cb_count = c + 1U;
    DIAG_LOW();
    diag_last_callback = bench_read_ccount() - whole_start;
    return work_width;''')
rep('''    ISR_MARKER_HIGH();
    ISR_MARKER_LOW();

    const uint32_t head = bench_head;''','''    ISR_MARKER_HIGH();
    ISR_MARKER_LOW();
    diag_isr_count++;

    const uint32_t head = bench_head;''')
rep('''            const uint32_t isr_cycles = bench_isr_ring[tail];
            const uint32_t period_cycles = bench_period_ring[tail];
            bench_tail = (tail + 1U) & BENCH_RING_MASK;''','''            const uint32_t isr_cycles = bench_isr_ring[tail];
            const uint32_t period_cycles = bench_period_ring[tail];
            bench_tail = (tail + 1U) & BENCH_RING_MASK;
            diag_last_ring_depth = (bench_head - bench_tail) & BENCH_RING_MASK;''')
rep('''            bench_entry_samples[n % BENCH_MAX_SAMPLES] = isr_cycles;
            bench_total_samples = n + 1U;''','''            bench_entry_samples[n % BENCH_MAX_SAMPLES] = isr_cycles;
            diag_flush_samples[n % BENCH_MAX_SAMPLES] = diag_last_flush;
            diag_callback_samples[n % BENCH_MAX_SAMPLES] = diag_last_callback;
            diag_load_isr_samples[n % BENCH_MAX_SAMPLES] = diag_last_load_isrs;
            diag_flush_isr_samples[n % BENCH_MAX_SAMPLES] = diag_last_flush_isrs;
            diag_ringdepth_samples[n % BENCH_MAX_SAMPLES] = diag_last_ring_depth;
            bench_total_samples = n + 1U;''')
rep('''void bench_export_raw_csv() {''','''void bench_export_raw_csv() {''')
# make G export diagnostic data after original g (raw export has already stopped timer)
rep('''void bench_clear_stats() {''','''void diag_export_csv() {
    // stop acquisition and retain original export format for existing Python scripts
    bench_export_raw_csv();
    const uint32_t total = bench_total_samples;
    const uint32_t n = total < BENCH_MAX_SAMPLES ? total : BENCH_MAX_SAMPLES;
    const uint32_t first = total - n;
    Serial.printf("BEGIN_DIAG,cache_mode=%u,flush_enabled=%u,retained=%lu\\n",
                  (unsigned)active_cache_mode, (unsigned)diag_do_cache_flush, (unsigned long)n);
    Serial.println("index,flush_cycles,full_callback_cycles,isr_during_flush,isr_during_load,ring_depth_after_pop");
    for (uint32_t i=0;i<n;i++) {
        const uint32_t slot = (first+i)%BENCH_MAX_SAMPLES;
        Serial.printf("%lu,%lu,%lu,%lu,%lu,%lu\\n", (unsigned long)(first+i),
          (unsigned long)diag_flush_samples[slot], (unsigned long)diag_callback_samples[slot],
          (unsigned long)diag_flush_isr_samples[slot], (unsigned long)diag_load_isr_samples[slot],
          (unsigned long)diag_ringdepth_samples[slot]);
        if ((i & 31U)==31U) delay(1);
    }
    Serial.println("END_DIAG"); Serial.flush();
}

void bench_clear_stats() {''')
rep('''    bench_last_isr_cycles = 0;
    bench_head = 0;''','''    bench_last_isr_cycles = 0;
    diag_isr_count = 0;
    bench_head = 0;''')
# SPI prerecord: GPIO26 HIGH at pre_cb, low immediate before hardware start
rep('''static void IRAM_ATTR spi_post_cb(spi_transaction_t *t) {''','''static void IRAM_ATTR spi_pre_cb(spi_transaction_t *t) {
    (void)t;
    diag_spi_pre_cycles = bench_read_ccount();
    diag_spi_pre_count++;
    DIAG_HIGH(); DIAG_LOW(); // pre-transaction driver callback, not first actual SCLK
}

static void IRAM_ATTR spi_post_cb(spi_transaction_t *t) {''')
rep('''    spi_cb_count = 0;
    isr_cycles_sum = 0;''','''    spi_cb_count = 0;
    diag_spi_pre_count = 0;
    diag_spi_pre_cycles = 0;
    isr_cycles_sum = 0;''')
rep('''    Serial.printf("  queue CPU time     : %.2f us\\n", setup_us);''','''    Serial.printf("  queue CPU time     : %.2f us\\n", setup_us);
    Serial.printf("  pre_cb count       : %lu (A8/ GPIO26 short pulse; pre_cb is not SCLK start)\\n",
                  (unsigned long)diag_spi_pre_count);
    // pre_cb may run in a different CPU core from run_dma; do NOT subtract
    // CCOUNT across cores. Use analyzer time differences instead.''')
rep('''    dev.post_cb = spi_post_cb;''','''    dev.pre_cb = spi_pre_cb;
    dev.post_cb = spi_post_cb;''')
# DAC instrumentation with wrapper to reduce boilerplate
rep('''void dma_feeder(void *pv) {''','''static esp_err_t diag_dac_write(const uint8_t *buf, size_t bytes, size_t *written) {
    const uint32_t t0 = bench_read_ccount();
    DIAG_HIGH(); // A8 shows blocking dac_continuous_write(), NOT output clocking.
    esp_err_t err = dac_continuous_write(dac_h, buf, bytes, written, pdMS_TO_TICKS(1000));
    DIAG_LOW();
    uint32_t dt = bench_read_ccount() - t0;
    diag_dac_write_calls++;
    diag_dac_write_ccount_total += dt;
    if (dt > diag_dac_write_ccount_max) diag_dac_write_ccount_max = dt;
    return err;
}

void dma_feeder(void *pv) {''')
rep('''        if (force_dma_underrun && (blk % 200U) == 100U) {
            MARKER_HIGH();''','''        if (force_dma_underrun && (blk % 200U) == 100U) {
            diag_dac_stalls++;
            MARKER_HIGH();''')
rep('''            bool high_step = ((blk & 0x10U) != 0);''','''            bool high_step = ((blk & 0x10U) != 0);
            if ((blk & 0x0fU)==0U) diag_dac_steps++;''')
# all three DAC writes
src=src.replace('dac_continuous_write(dac_h, dac_dma_staging, n_local * 2, &w, pdMS_TO_TICKS(1000))','diag_dac_write(dac_dma_staging, n_local * 2, &w)')
if src.count('diag_dac_write(dac_dma_staging, n_local * 2, &w)')!=2: raise RuntimeError('dac write replacement unexpected')
rep('''    dac_bytes_submitted = 0;
    dma_latency_test = lat_test;''','''    dac_bytes_submitted = 0;
    diag_dac_stalls = diag_dac_steps = diag_dac_write_calls = 0;
    diag_dac_write_ccount_total = 0; diag_dac_write_ccount_max = 0;
    dma_latency_test = lat_test;''')
rep('''    pinMode(PIN_INTR, OUTPUT);''','''    pinMode(PIN_DIAG, OUTPUT);
    gpio_set_direction((gpio_num_t)PIN_DIAG, GPIO_MODE_OUTPUT);
    DIAG_LOW();
    pinMode(PIN_INTR, OUTPUT);''')
rep('''            case 'g':
                bench_export_raw_csv();
                break;''','''            case 'g':
                bench_export_raw_csv();
                break;
            case 'G':
                diag_export_csv();
                break;
            case 'F':
                kill_tasks(); ensure_gpt_stopped();
                diag_do_cache_flush = !diag_do_cache_flush;
                Serial.printf("Diagnostic explicit cache flush: %s\\n", diag_do_cache_flush ? "ON" : "OFF");
                break;''')
rep('''                Serial.println("Note: successful writes prove DAC driver acceptance, NOT analog signal integrity or absence of FIFO underrun.");''','''                Serial.printf("DAC diagnostic: stalls=%lu, step changes=%lu, write calls=%lu, "
                              "mean blocking write=%.3f us, max=%.3f us\\n",
                              (unsigned long)diag_dac_stalls, (unsigned long)diag_dac_steps,
                              (unsigned long)diag_dac_write_calls,
                              diag_dac_write_calls ? (double)diag_dac_write_ccount_total / diag_dac_write_calls / CPU_FREQ_MHZ : 0.0,
                              (double)diag_dac_write_ccount_max / CPU_FREQ_MHZ);
                Serial.println("Note: successful writes prove DAC driver acceptance, NOT analog signal integrity or absence of FIFO underrun.");''')
rep('''    Serial.println("[g] Export raw timer samples as CSV (stops acquisition first)");''','''    Serial.println("[g] Export original CSV | [G] Export original + diagnostic flush/full-callback/ring-depth CSV");
    Serial.println("[F] Toggle whole-cache invalidation (default ON; only for controlled comparisons)");
    Serial.println("Diagnostic GPIO26: full cache callback / SPI pre_cb / synchronous DAC write.");''')
out=Path('/mnt/data/esp32_benchmark_DIAGNOSTIC.ino');out.write_text(src)
print('created',out, len(src),'bytes')
