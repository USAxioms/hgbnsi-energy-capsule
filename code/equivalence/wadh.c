#include <stdio.h>
#include <stdlib.h>
#include "wad18.h"
static wad_t rd(const char*s){int neg=*s=='-';if(neg)s++;unsigned __int128 v=0;while(*s)v=v*10+(*s++-'0');return neg?-(wad_t)v:(wad_t)v;}
static void pr(wad_t x){char b[64];wad_int_to_string(x,b,64);printf("%s",b);}
int main(){char a[64],b[64];while(scanf("%63s %63s",a,b)==2){wad_t x=rd(a),y=rd(b),r;wad_err e=wad_mul(x,y,&r);printf("%d ",e);if(!e)pr(r);else printf("-");printf(" ");e=wad_div(x,y,&r);printf("%d ",e);if(!e)pr(r);else printf("-");printf("\n");}}
