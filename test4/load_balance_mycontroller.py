#!/usr/bin/env python3
import argparse
import grpc
import os
import sys
from time import sleep

# Import P4Runtime lib from parent utils dir
# Probably there's a better way of doing this.
sys.path.append(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 '../../utils/'))
import p4runtime_lib.bmv2
from p4runtime_lib.error_utils import printGrpcError
from p4runtime_lib.switch import ShutdownAllSwitchConnections
import p4runtime_lib.helper


def getHashValue(p4_info_helper, swIngress, swEgress,
                 dstIPAddr, ecmp_base, ecmp_count):
    table_entry = p4_info_helper.buildTableEntry(
        table_name="MyIngress.ecmp_group",
        match_fields={
            "hdr.ipv4.dstAddr": dstIPAddr
        },
        action_name="MyIngress.set_ecmp_select",
        action_params={
            "ecmp_base": ecmp_base,
            "ecmp_count": ecmp_count
        })
    swEgress.WriteTableEntry(table_entry)


def matchHashValue(p4_info_helper, swIngress, swEgress,
                   ecmp_select, nhop_dmac, nhop_ipv4, port):
    table_entry = p4_info_helper.buildTableEntry(
        table_name="MyIngress.ecmp_nhop",
        match_fields={
            "meta.ecmp_select": ecmp_select
        },
        action_name="MyIngress.set_nhop",
        action_params={
            "nhop_dmac": nhop_dmac,
            "nhop_ipv4": nhop_ipv4,
            "port": port
        })
    swEgress.WriteTableEntry(table_entry)


def sendFrame(p4_info_helper, swIngress, swEgress,
              egress_port, smac):
    table_entry = p4_info_helper.buildTableEntry(
        table_name="MyEgress.send_frame",
        match_fields={
            "standard_metadata.egress_port": egress_port
        },
        action_name="MyEgress.rewrite_mac",
        action_params={
            "smac": smac
        })
    swEgress.WriteTableEntry(table_entry)


def main(p4info_file_path, bmv2_file_path):
    # Instantiate a P4Runtime helper from the p4info file
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file_path)

    try:
        # Create a switch connection object for s1 and s2;
        # this is backed by a P4Runtime gRPC connection.
        # Also, dump all P4Runtime messages sent to switch to given txt files.
        s1 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s1',
            address='127.0.0.1:50051',
            device_id=0,
            proto_dump_file='logs/s1-p4runtime-requests.txt')
        s2 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s2',
            address='127.0.0.1:50052',
            device_id=1,
            proto_dump_file='logs/s2-p4runtime-requests.txt')
        s3 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s3',
            address='127.0.0.1:50053',
            device_id=2,
            proto_dump_file='logs/s3-p4runtime-requests.txt')

        # Send master arbitration update message to establish this controller as
        # master (required by P4Runtime before performing any other write operation)
        s1.MasterArbitrationUpdate()
        s2.MasterArbitrationUpdate()
        s3.MasterArbitrationUpdate()

        # Install the P4 program on the switches
        s1.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        s2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        s3.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)

        # s1
        getHashValue(p4info_helper, swIngress=s1, swEgress=s1, dstIPAddr=["10.0.0.1", 32], ecmp_base=0, ecmp_count=2)
        matchHashValue(p4info_helper, swIngress=s1, swEgress=s1, ecmp_select=0, nhop_dmac="00:00:00:00:01:02",
                       nhop_ipv4="10.0.2.2", port=2)
        matchHashValue(p4info_helper, swIngress=s1, swEgress=s1, ecmp_select=1, nhop_dmac="00:00:00:00:01:03",
                       nhop_ipv4="10.0.3.3", port=3)
        sendFrame(p4info_helper, swIngress=s1, swEgress=s1, egress_port=2, smac="00:00:00:01:02:00")
        sendFrame(p4info_helper, swIngress=s1, swEgress=s1, egress_port=3, smac="00:00:00:01:03:00")

        # s2
        getHashValue(p4info_helper, swIngress=s2, swEgress=s2, dstIPAddr=["10.0.2.2", 32], ecmp_base=0, ecmp_count=1)
        matchHashValue(p4info_helper, swIngress=s2, swEgress=s2, ecmp_select=0, nhop_dmac="00:00:00:00:02:02",
                       nhop_ipv4="10.0.2.2", port=1)
        sendFrame(p4info_helper, swIngress=s2, swEgress=s2, egress_port=1, smac="00:00:00:02:01:00")

        # s3
        getHashValue(p4info_helper, swIngress=s3, swEgress=s3, dstIPAddr=["10.0.3.3", 32], ecmp_base=0, ecmp_count=1)
        matchHashValue(p4info_helper, swIngress=s3, swEgress=s3, ecmp_select=0, nhop_dmac="00:00:00:00:03:03",
                       nhop_ipv4="10.0.3.3", port=1)
        sendFrame(p4info_helper, swIngress=s3, swEgress=s3, egress_port=1, smac="00:00:00:03:01:00")

    except KeyboardInterrupt:
        print(" Shutting down.")
    except grpc.RpcError as e:
        printGrpcError(e)

    ShutdownAllSwitchConnections()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='./build/load_balance.p4.p4info.txt')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='./build/load_balance.json')
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print("\np4info file not found: %s\nHave you run 'make'?" % args.p4info)
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print("\nBMv2 JSON file not found: %s\nHave you run 'make'?" % args.bmv2_json)
        parser.exit(1)
    main(args.p4info, args.bmv2_json)