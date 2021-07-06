#!/usr/bin/env python
"""AFF4 RDFValue implementations for Android client information.

This module contains the RDFValue implementations used to communicate with the
client.
"""

from grr.lib import rdfvalue
from grr.lib.rdfvalues import client
from grr.lib.rdfvalues import crypto
from grr.lib.rdfvalues import structs
from grr.lib.rdfvalues import protodict
from grr.proto import android_pb2


class AndroidHardwareInfo(structs.RDFProtoStruct):
    """Information about Android device hardware, which usually appears in Settings APP"""
    protobuf = android_pb2.AndroidHardwareInfo


class AndroidOsBuildInfo(structs.RDFProtoStruct):
    """Build information about Android OS, which usually appears in Settings APP"""
    protobuf = android_pb2.AndroidOsBuildInfo
    rdf_deps = [
        rdfvalue.RDFDatetime,
    ]


class AndroidOsInfo(structs.RDFProtoStruct):
    """Information about Android OS, which usually appears in Settings APP"""
    protobuf = android_pb2.AndroidOsInfo
    rdf_deps = [
        android_pb2.AndroidOsBuildInfo
    ]


class AndroidDeviceInfo(structs.RDFProtoStruct):
    """Information about Android device and OS that needs to be collected on interrogation"""
    protobuf = android_pb2.AndroidDeviceInfo
    rdf_deps = [
        android_pb2.AndroidHardwareInfo,
        android_pb2.AndroidOsInfo,
    ]


class AndroidPackageInfo(structs.RDFProtoStruct):
    """Android package information"""
    protobuf = android_pb2.AndroidPackageInfo
    rdf_deps = [
        rdfvalue.RDFDatetime,
        crypto.RDFX509Cert
    ]


class AndroidBatteryInfo(structs.RDFProtoStruct):
    """Android battery information"""
    protobuf = android_pb2.AndroidBatteryInfo


class AndroidStorageInfo(structs.RDFProtoStruct):
    """Android storage volume information"""
    protobuf = android_pb2.AndroidStorageInfo
    rdf_deps = [
        rdfvalue.ByteSize
    ]


class AndroidWiFiConnectionInfo(structs.RDFProtoStruct):
    """Android device WiFi connection information"""
    protobuf = android_pb2.AndroidWiFiConnectionInfo
    rdf_deps = [
        client.MacAddress,
        client.NetworkAddress
    ]


class AndroidDhcpInfo(structs.RDFProtoStruct):
    """DHCP information about a network on an Android device"""
    protobuf = android_pb2.AndroidDhcpInfo
    rdf_deps = [
        rdfvalue.RDFDatetimeSeconds,
        client.NetworkAddress
    ]


class AndroidWiFiConfiguration(structs.RDFProtoStruct):
    """Information about saved WiFi network on an Android device"""
    protobuf = android_pb2.AndroidWiFiConfiguration


class AndroidWiFiScanResult(structs.RDFProtoStruct):
    """Android WiFi AP scanning result"""
    protobuf = android_pb2.AndroidWiFiScanResult
    rdf_deps = [
        rdfvalue.RDFDatetime
    ]


class AndroidWiFiInfo(structs.RDFProtoStruct):
    """Android saved WiFi configurations, WiFi connection information, and AP scanning results."""
    protobuf = android_pb2.AndroidWiFiInfo
    rdf_deps = [
        android_pb2.AndroidWiFiConnectionInfo,
        android_pb2.AndroidDhcpInfo,
        android_pb2.AndroidWiFiConfiguration,
        android_pb2.AndroidWiFiScanResult
    ]


class AndroidCellInfo(structs.RDFProtoStruct):
    """Telephony cell information from a point in time."""
    protobuf = android_pb2.AndroidCellInfo
    rdf_deps = [
        rdfvalue.RDFDatetime
    ]


class AndroidSubscriptionInfo(structs.RDFProtoStruct):
    """Information about the current Telephony subscriptions."""
    protobuf = android_pb2.AndroidSubscriptionInfo


class AndroidTelephonyInfo(structs.RDFProtoStruct):
    """Information about the current Telephony subscriptions."""
    protobuf = android_pb2.AndroidTelephonyInfo
    rdf_deps = [
        android_pb2.AndroidCellInfo,
        android_pb2.AndroidSubscriptionInfo
    ]


class AndroidBluetoothDevice(structs.RDFProtoStruct):
    """Detail information of a bonded or nearby Bluetooth device."""
    protobuf = android_pb2.AndroidBluetoothDevice
    rdf_deps = [
        client.MacAddress
    ]


class AndroidBluetoothInfo(structs.RDFProtoStruct):
    """Detail information of the built-in Bluetooth adapter and bonded or nearby Bluetooth device."""
    protobuf = android_pb2.AndroidBluetoothInfo
    rdf_deps = [
        android_pb2.AndroidBluetoothDevice,
        client.MacAddress
    ]


class AndroidPhoneNumber(structs.RDFProtoStruct):
    """Phone number of a contact on an Android device."""
    protobuf = android_pb2.AndroidContactInfo.AndroidPhoneNumber


class AndroidEmailAddress(structs.RDFProtoStruct):
    """Email address of a contact on an Android device."""
    protobuf = android_pb2.AndroidContactInfo.AndroidEmailAddress


class AndroidPostalAddress(structs.RDFProtoStruct):
    """Postal address of a contact on an Android device."""
    protobuf = android_pb2.AndroidContactInfo.AndroidPostalAddress


class AndroidIM(structs.RDFProtoStruct):
    """Instant message information of a contact on an Android device."""
    protobuf = android_pb2.AndroidContactInfo.AndroidIM


class AndroidContactInfo(structs.RDFProtoStruct):
    """Contact information on a mobile device."""
    protobuf = android_pb2.AndroidContactInfo
    rdf_deps = [
        android_pb2.AndroidContactInfo.AndroidPhoneNumber,
        android_pb2.AndroidContactInfo.AndroidEmailAddress,
        android_pb2.AndroidContactInfo.AndroidPostalAddress,
        android_pb2.AndroidContactInfo.AndroidIM
    ]


class AndroidCallLog(structs.RDFProtoStruct):
    """Detail information of a phone call on an Android device."""
    protobuf = android_pb2.AndroidCallLog
    rdf_deps = [
        rdfvalue.RDFDatetime,
        rdfvalue.Duration
    ]


class AndroidSmsMmsBody(structs.RDFProtoStruct):
    """The body part of a SMS/MMS message."""
    protobuf = android_pb2.AndroidSmsMmsBody


class AndroidSmsMms(structs.RDFProtoStruct):
    """A Short Message Service (SMS) or Multimedia Messaging Service (MMS) message"""
    protobuf = android_pb2.AndroidSmsMms
    rdf_deps = [
        android_pb2.AndroidSmsMmsBody,
        rdfvalue.RDFDatetime
    ]


class AndroidLocation(structs.RDFProtoStruct):
    """The location of an Android device."""
    protobuf = android_pb2.AndroidLocation
    rdf_deps = [
        rdfvalue.RDFDatetime
    ]


class AndroidSystemSettings(structs.RDFProtoStruct):
    """Android system settings."""
    protobuf = android_pb2.AndroidSystemSettings
    rdf_deps = [
        protodict.Dict
    ]


class AndroidSensorInfo(structs.RDFProtoStruct):
    """Details about a sensor on an Android device."""
    protobuf = android_pb2.AndroidSensorInfo


class AndroidSensorDataRequest(structs.RDFProtoStruct):
    """Request for dumping sensor data of an Android device."""
    protobuf = android_pb2.AndroidSensorDataRequest


class AndroidSensorData(structs.RDFProtoStruct):
    """Details, including values, of the sensor data."""
    protobuf = android_pb2.AndroidSensorData


class AndroidSensorDataResponse(structs.RDFProtoStruct):
    """Sensor data collection results."""
    protobuf = android_pb2.AndroidSensorDataResponse
    rdf_deps = [
        rdfvalue.RDFDatetime,
        android_pb2.AndroidSensorData
    ]


class AndroidNfcInfo(structs.RDFProtoStruct):
    """NFC hardware information of an Android device."""
    protobuf = android_pb2.AndroidNfcInfo


class AndroidAccount(structs.RDFProtoStruct):
    """Details of an user account."""
    protobuf = android_pb2.AndroidAccount


class AndroidAccountAuthenticator(structs.RDFProtoStruct):
    """Information about an account authenticator."""
    protobuf = android_pb2.AndroidAccountAuthenticator


class AndroidAccountInfo(structs.RDFProtoStruct):
    """Information about user accounts and authenticators."""
    protobuf = android_pb2.AndroidAccountInfo
    rdf_deps = [
        android_pb2.AndroidAccount,
        android_pb2.AndroidAccountAuthenticator
    ]


class AndroidUserProfile(structs.RDFProtoStruct):
    """Information about an Android device user."""
    protobuf = android_pb2.AndroidUserProfile
    rdf_deps = [
        rdfvalue.RDFDatetime
    ]


class AndroidVpnProfile(structs.RDFProtoStruct):
    """Android VPN profile information."""
    protobuf = android_pb2.AndroidVpnProfile

