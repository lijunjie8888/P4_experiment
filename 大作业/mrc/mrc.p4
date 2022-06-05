/* -*- P4_16 -*- */
#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4 = 0x800;


/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/
/*数据格式定义部分*/
typedef bit<9>  egressSpec_t; //根据各个字段的长度等信息，定义各种数据包头
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}


struct metadata {

}


struct headers {
    ethernet_t   ethernet;
    ipv4_t       ipv4;
}

/*************************************************************************
*********************** P A R S E R  ***********************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition parse_ethernet;    //转移到EthernetParse状态
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);  //提取以太包头
        transition select(hdr.ethernet.etherType) { //根据etherType, 选择转移到其他状态，直到转移到accept;
            TYPE_IPV4: parse_ipv4;     //如果是0x0800,则转移到parse_ipv4状态
            default: accept;           //默认是接受，进入下一步处理
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);    //提取ip包头
        transition accept;
    }


}


/*************************************************************************
************   C H E C K S U M    V E R I F I C A T I O N   *************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {  }
}


/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {
    action drop() {
        mark_to_drop(standard_metadata); ////内置函数，将当前数据包标记为即将丢弃数据包
    }

    action ipv4_forward(macAddr_t dstAddr, egressSpec_t port) {
        standard_metadata.egress_spec = port;         //将输出的端口从参数中取出，参数是由控制面配置
        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;  //原始数据包的源地址改为目的地址
        hdr.ethernet.dstAddr = dstAddr;               //目的地址改为控制面传入的新地址
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;              //ttl递减
    }

    table ipv4_lpm { //定义一张表
        key = { //流表匹配域关键字
            hdr.ipv4.dstAddr: lpm; //匹配模式（lpm是最长前缀匹配，exact是精准匹配，ternary是三元匹配）
        }
        actions = { //流表动作集合
            ipv4_forward;  //转发数据，需要自定义
            drop;          //丢弃动作
            NoAction;      //空动作
        }
        size = 1024;       //流表可以容纳最大流表项
        default_action = drop();   //默认动作为丢弃
    }

    table ipv4_lpm_2 { //定义一张表
        key = { //流表匹配域关键字
            hdr.ipv4.dstAddr: lpm; //匹配模式（lpm是最长前缀匹配，exact是精准匹配，ternary是三元匹配）
        }
        actions = { //流表动作集合
            ipv4_forward;  //转发数据，需要自定义
            drop;          //丢弃动作
            NoAction;      //空动作
        }
        size = 1024;       //流表可以容纳最大流表项
        default_action = drop();   //默认动作为丢弃
    }

    table ipv4_lpm_3 { //定义一张表
        key = { //流表匹配域关键字
            hdr.ipv4.dstAddr: lpm; //匹配模式（lpm是最长前缀匹配，exact是精准匹配，ternary是三元匹配）
        }
        actions = { //流表动作集合
            ipv4_forward;  //转发数据，需要自定义
            drop;          //丢弃动作
            NoAction;      //空动作
        }
        size = 1024;       //流表可以容纳最大流表项
        default_action = drop();   //默认动作为丢弃
    }


    apply {
        if (hdr.ipv4.isValid()) {

            if(hdr.ipv4.diffserv == 0){
            ipv4_lpm.apply();
      }
            else if(hdr.ipv4.diffserv == 4){
                ipv4_lpm_2.apply();
            }
            else{
                ipv4_lpm_3.apply();
            }
        }
    }
}

/*************************************************************************
****************  E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply {  }
}

/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
     apply {
        update_checksum(
            hdr.ipv4.isValid(),
            { hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}


/*************************************************************************
***********************  D E P A R S E R  *******************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {     //注意封包的先后顺序
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
    }
}

/*************************************************************************
***********************  S W I T C H  *******************************
*************************************************************************/

V1Switch(
MyParser(),         //解析数据包，提取包头
MyVerifyChecksum(), //校验和验证
MyIngress(),        //输入处理
MyEgress(),         //输出处理
MyComputeChecksum(), //计算新的校验和
MyDeparser()         //逆解析器
) main;
