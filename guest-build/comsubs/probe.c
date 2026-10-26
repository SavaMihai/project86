/* Guest-only comparison harness, linked separately with old/new COMSUBS.
 * Each process handles eight records: the original COMSUBS initialization leaks
 * tables because its source-provided DosCaseMap wrapper leaves AX nonzero.
 * Process isolation keeps that unrelated defect out of interface comparisons.
 */
#include <stdio.h>
#include <stdlib.h>
#include "comsub.h"
extern void test_install(void);
extern void test_restore(void);
struct Query { unsigned char text[32], pattern[16]; unsigned word; };

int main(int argc, char **argv)
{
    FILE *input, *output;
    struct Query q;
    unsigned result[256], i, j, count;
    volatile unsigned value;
    unsigned char *p;
    if (argc != 4) return 2;
    output = fopen(argv[3], "ab");
    if (!output) return 3;
    if (argv[1][0] == 'R') {
        i = 0;
        do {
            for (j = 0; j < 256; j++) { value = rctomid(i++); result[j] = value; }
            if (fwrite(result, 2, 256, output) != 256) return 4;
        } while (i);
    } else {
        input = fopen("QUERY.BIN", "rb");
        if (!input) return 5;
        if (fseek(input, (long)atoi(argv[1]) * sizeof(q), 0)) return 6;
        if (argv[2][0] == '1') test_install();
        for (count = 0; count < 8 && fread(&q, sizeof(q), 1, input) == 1; count++) {
            p = (unsigned char *)com_strchr(q.text, (unsigned char)q.word);
            result[0] = p ? p - q.text : 0xffff;
            p = com_strrchr(q.text, (unsigned char)q.word);
            result[1] = p ? p - q.text : 0xffff;
            p = com_substr(q.text, q.pattern);
            result[2] = p ? p - q.text : 0xffff;
            value = com_toupper((unsigned char)q.word); result[3] = value;
            value = rctomid(q.word); result[4] = value;
            if (fwrite(result, 2, 5, output) != 5 || fwrite(&q, sizeof(q), 1, output) != 1) return 7;
        }
        if (argv[2][0] == '1') test_restore();
        fclose(input);
    }
    if (fclose(output)) return 8;
    return 0;
}
