#include <stdio.h>
#include <string.h>
#include "wad18.h"
int main(){char line[256];while(fgets(line,256,stdin)){line[strcspn(line,"\n")]=0;wad_t v;wad_err e=wad_parse(line,&v);char b[64];if(!e){wad_int_to_string(v,b,64);printf("OK %s\n",b);}else printf("ERR\n");}}
