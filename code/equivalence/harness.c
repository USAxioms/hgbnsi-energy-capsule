#include <stdio.h>
#include "ssi.h"
int main(void){
  /* permit13: all 8192 */
  for(unsigned b=0;b<8192;b++) printf("P %u %d\n",b,ssi_permit13_from_bits(b));
  /* decide */
  for(int a=0;a<2;a++)for(int v=0;v<3;v++)for(int p=0;p<2;p++) printf("D %d %d %d %d\n",a,v,p,ssi_decide(a,(ver_result)v,p));
  /* transitions */
  for(int f=0;f<6;f++)for(int t=0;t<6;t++) printf("T %d %d %d\n",f,t,ssi_can_transition(f,t));
  /* adopt6 */
  for(unsigned m=0;m<64;m++) printf("A %u %d\n",m,ssi_adopt6(m&1,m>>1&1,m>>2&1,m>>3&1,m>>4&1,m>>5&1));
  /* mediate */
  for(int k=-1;k<12;k++)for(int p=0;p<2;p++) printf("M %d %d %d\n",k,p,ssi_mediate((action_type)k,p));
  /* capability */
  for(unsigned n=0;n<16;n++)for(unsigned a=0;a<16;a++)for(int g=0;g<2;g++) printf("C %u %u %d %d\n",n,a,g,ssi_capability_ok(n,a,g));
  /* non-regression: 3 invariants, all truth combos */
  for(int x=0;x<27;x++)for(int y=0;y<27;y++){ssi_truth b[3],a[3];int xx=x,yy=y;for(int i=0;i<3;i++){b[i]=xx%3;a[i]=yy%3;xx/=3;yy/=3;} printf("N %d %d %d\n",x,y,ssi_non_regression(b,a,3));}
  /* vs */
  for(int n=0;n<4;n++)for(int x=0;x<27;x++){ssi_truth t[3];int xx=x;for(int i=0;i<3;i++){t[i]=xx%3;xx/=3;} printf("V %d %d %d\n",n,x,ssi_vs(t,n));}
  /* verify: all 2^11 */
  for(unsigned c=0;c<2048;c++){ssi_verify_input in={c&1,c>>1&1,c>>2&1,c>>3&1,c>>4&1,c>>5&1,c>>6&1,c>>7&1,c>>8&1,c>>9&1,c>>10&1};const char*r=ssi_verify(&in);printf("Y %u %s\n",c,r?r:"PASS");}
  /* directive + csl over small grids */
  for(int s=0;s<2;s++)for(int i=0;i<3;i++)for(int e=0;e<3;e++)for(int r=0;r<3;r++)for(int n=0;n<3;n++)for(int c=0;c<3;c++)for(int sc=0;sc<2;sc++)
    printf("R %d %d %d %d %d %d %d %d\n",s,i,e,r,n,c,sc,ssi_directive_valid(s,i,e,r,n,c,sc));
  for(int s=0;s<2;s++)for(int rv=0;rv<2;rv++)for(int u=0;u<3;u++)for(int n=0;n<3;n++)for(int en=0;en<2;en++)
    printf("L %d %d %d %d %d %d\n",s,rv,u,n,en,ssi_csl_auth(s,rv,u,n,en));
  return 0;}
