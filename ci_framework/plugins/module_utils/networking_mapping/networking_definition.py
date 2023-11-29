from __future__ import annotations

import dataclasses
import ipaddress
import typing

from ansible_collections.cifmw.general.plugins.module_utils.networking_mapping import (
    exceptions,
)


def _raise_missing_field(
    value: typing.Any, field_name: str, parent_name: str = None, parent_type: str = None
):
    if not value:
        raise exceptions.NetworkMappingValidationError(
            f"'{field_name}' field is mandatory",
            field=field_name,
            invalid_value=value,
            parent_name=parent_name,
            parent_type=parent_type,
        )


def _validate_parse_int(
    field_name: str,
    raw_definition: typing.Dict[str, typing.Any],
    parent_name: str = None,
    parent_type: str = None,
    mandatory: bool = False,
    min_value: typing.Union[int, None] = None,
    max_value: typing.Union[int, None] = None,
) -> typing.Union[int, None]:
    if (not mandatory) and field_name not in raw_definition:
        return None
    elif field_name not in raw_definition:
        _raise_missing_field(
            None, field_name, parent_name=parent_name, parent_type=parent_type
        )
    raw_value = raw_definition[field_name]
    try:
        value = int(raw_value)
        if min_value is not None and value < min_value:
            raise exceptions.NetworkMappingValidationError(
                f"Invalid {field_name} value. Value is less than {min_value}",
                field=field_name,
                invalid_value=raw_value,
                parent_name=parent_name,
                parent_type=parent_type,
            )
        if max_value is not None and value > max_value:
            raise exceptions.NetworkMappingValidationError(
                f"Invalid {field_name} value. Value is more than {max_value}",
                field=field_name,
                invalid_value=raw_value,
            )
        return value
    except ValueError as err:
        raise exceptions.NetworkMappingValidationError(
            f"{raw_value} is not a valid integer",
            field=field_name,
            invalid_value=raw_value,
            parent_name=parent_name,
            parent_type=parent_type,
        ) from err


def _validate_parse_field_type(
    field_name: str,
    raw_definition: typing.Dict[str, typing.Any],
    expected_type: typing.Type,
    parent_name: str = None,
    parent_type: str = None,
    mandatory: bool = False,
) -> typing.Any:
    if (not mandatory) and field_name not in raw_definition:
        return None
    elif field_name not in raw_definition:
        _raise_missing_field(
            None, field_name, parent_name=parent_name, parent_type=parent_type
        )

    raw_value = raw_definition[field_name]
    if not isinstance(raw_value, expected_type):
        raise exceptions.NetworkMappingValidationError(
            f"'{field_name}' must be of type {expected_type}",
            field=field_name,
            invalid_value=str(raw_value),
            parent_name=parent_name,
            parent_type=parent_type,
        )
    return raw_value


def check_host_network_ranges_collisions(ranges: typing.List[HostNetworkRange]):
    ranges.sort(key=lambda x: x.start_host, reverse=False)
    for index in range(0, len(ranges) - 1):
        start = ranges[index].start_host
        length = ranges[index].length
        next_start = ranges[index + 1].start_host
        if (start + length) > next_start:
            return ranges[index], ranges[index + 1]
    return None, None


class HostNetworkRange:
    __FIELD_RANGE_START = "start"
    __FIELD_RANGE_END = "end"
    __FIELD_RANGE_LENGTH = "length"

    def __init__(
        self,
        network: typing.Union[ipaddress.IPv4Network, ipaddress.IPv6Network],
        start: typing.Union[
            ipaddress.IPv4Address, ipaddress.IPv6Address, str, int, None
        ] = None,
        end: typing.Union[
            ipaddress.IPv4Address, ipaddress.IPv6Address, str, int, None
        ] = None,
        length: int = None,
    ):
        if not network:
            raise exceptions.NetworkMappingValidationError(
                "network is a mandatory argument"
            )
        self.__network = network
        self.__init_range_start(start)
        self.__init_range_end(end, length)

        if self.__start_ip > self.__end_ip:
            raise exceptions.NetworkMappingValidationError(
                f"range end {self.__end_ip} for {self.__network} "
                f"cannot be less than {self.__start_ip}",
                invalid_value=end,
                field=self.__FIELD_RANGE_END,
            )

    def __init_range_end(self, end, length):
        parsed_end, end_is_ip = self.__parse_validate_range_limit(
            end, self.__FIELD_RANGE_END
        )
        if parsed_end and end_is_ip and parsed_end not in self.__network:
            raise exceptions.NetworkMappingValidationError(
                f"Range end IP {end} is out of range of {self.__network} network",
                invalid_value=end,
                field=self.__FIELD_RANGE_END,
            )
        if length is not None and (not end_is_ip) and (not parsed_end):
            try:
                if int(length) < 1:
                    raise exceptions.NetworkMappingValidationError(
                        f"length {length} for {self.__network} "
                        "network should be positive",
                        invalid_value=length,
                        field=self.__FIELD_RANGE_LENGTH,
                    )

                self.__length = int(length)
                self.__end_ip = self.__network[self.__length + self.start_host - 1]
            except IndexError as err:
                raise exceptions.NetworkMappingValidationError(
                    f"length {length} is out of range of {self.__network} network",
                    invalid_value=length,
                    field=self.__FIELD_RANGE_LENGTH,
                ) from err
            except ValueError as err:
                raise exceptions.NetworkMappingValidationError(
                    f"length {length} is not a valid integer",
                    invalid_value=length,
                    field=self.__FIELD_RANGE_LENGTH,
                ) from err
        elif parsed_end and end_is_ip:
            self.__end_ip = parsed_end
            self.__length = int(self.__end_ip) - int(self.__start_ip) + 1
        elif parsed_end and not end_is_ip:
            try:
                self.__length = parsed_end - self.__start_host + 1
                self.__end_ip = self.__network[parsed_end]
            except IndexError as err:
                raise exceptions.NetworkMappingValidationError(
                    f"end {parsed_end} is out of range of {self.__network} network",
                    invalid_value=end,
                    field=self.__FIELD_RANGE_END,
                ) from err
        else:
            self.__end_ip = self.__network[-1]
            self.__length = self.__network.num_addresses

    def __init_range_start(self, start):
        parsed_start, start_is_ip = self.__parse_validate_range_limit(
            start, self.__FIELD_RANGE_START
        )
        if parsed_start and start_is_ip and parsed_start not in self.__network:
            raise exceptions.NetworkMappingValidationError(
                f"Range start IP {start} is out of range of {self.__network} network",
                invalid_value=start,
                field=self.__FIELD_RANGE_START,
            )
        if parsed_start and not start_is_ip:
            self.__start_host = parsed_start
            try:
                self.__start_ip = self.__network[self.__start_host]
            except IndexError as err:
                raise exceptions.NetworkMappingValidationError(
                    f"Range start {parsed_start} is out of range "
                    f"of {self.__network} network",
                    invalid_value=start,
                    field=self.__FIELD_RANGE_START,
                ) from err
        elif parsed_start:
            self.__start_ip = parsed_start
            self.__start_host = int(self.__start_ip) - int(
                self.__network.network_address
            )
        else:
            self.__start_ip = self.__network[0]
            self.__start_host = 0

    def __parse_validate_range_limit(
        self,
        value: typing.Union[ipaddress.IPv4Address, ipaddress.IPv6Address, str],
        field_name: str,
    ) -> typing.Tuple[
        typing.Union[ipaddress.IPv4Address, ipaddress.IPv6Address, int, None], bool
    ]:
        if not value:
            return None, False
        if isinstance(value, ipaddress.IPv4Address) or isinstance(
            value, ipaddress.IPv6Address
        ):
            return value, True

        try:
            range_num_limit = int(value)
            if range_num_limit < 0:
                raise exceptions.NetworkMappingValidationError(
                    f"{field_name} {range_num_limit} is out of range "
                    f"of {self.__network} network",
                    invalid_value=value,
                    field=field_name,
                )
            return range_num_limit, False
        except ValueError:
            pass
        try:
            return ipaddress.ip_address(value), True
        except ValueError as err:
            raise exceptions.NetworkMappingValidationError(
                f"{self.__network.network_address} range contains a "
                f"{field_name} value, {value}, that not a valid",
                invalid_value=value,
                field=field_name,
            ) from err

    @property
    def start_host(self) -> int:
        return self.__start_host

    @property
    def length(self) -> int:
        return self.__length

    @property
    def start_ip(self) -> typing.Union[ipaddress.IPv4Address, ipaddress.IPv6Address]:
        return self.__start_ip

    @property
    def end_ip(self) -> typing.Union[ipaddress.IPv4Address, ipaddress.IPv6Address]:
        return self.__end_ip

    @property
    def network(self) -> typing.Union[ipaddress.IPv4Network, ipaddress.IPv6Network]:
        return self.__network

    def __contains__(self, element):
        ip = element
        try:
            ip = ipaddress.ip_address(element) if isinstance(element, str) else ip
        except ValueError:
            return False

        if (not isinstance(ip, ipaddress.IPv4Address)) and (
            not isinstance(ip, ipaddress.IPv6Address)
        ):
            return False

        return (
            ip in self.__network and (ip >= self.__start_ip) and (ip <= self.__end_ip)
        )

    @classmethod
    def from_raw(
        cls,
        network: typing.Union[ipaddress.IPv4Network, ipaddress.IPv6Network],
        raw_range: typing.Union[typing.Dict[str, typing.Any], str],
    ):
        if raw_range and not isinstance(raw_range, (dict, str)):
            raise exceptions.NetworkMappingValidationError(
                "raw_range argument must be a dict or a string",
                invalid_value=raw_range,
            )

        if isinstance(raw_range, str):
            range_split = raw_range.split("-")
            if len(range_split) != 2:
                raise exceptions.NetworkMappingValidationError(
                    f"range {raw_range} for {network} net "
                    "must be in the <START>-<END> format",
                    invalid_value=raw_range,
                )
            return HostNetworkRange(
                network,
                start=range_split[0],
                end=range_split[1],
            )

        return HostNetworkRange(
            network,
            start=raw_range.get(cls.__FIELD_RANGE_START, None),
            end=raw_range.get(cls.__FIELD_RANGE_END, None),
            length=raw_range.get(cls.__FIELD_RANGE_LENGTH, None),
        )

    def __hash__(self):
        return hash((self.__network, self.__start_ip, self.__end_ip))

    def __eq__(self, other):
        if not isinstance(other, HostNetworkRange):
            return False

        return (
            self.__start_ip == other.__start_ip
            and self.__network == other.__network
            and self.__end_ip == other.__end_ip
        )

    def __str__(self):
        return f"{self.__start_ip}-{self.__end_ip}"


class SubnetBasedNetworkToolDefinition:
    __FIELD_RANGES = "ranges"
    __FIELD_SINGLE_RANGE = "range"

    def __init__(
        self,
        network: NetworkDefinition,
        raw_config: typing.Dict[str, typing.Any],
        allow_multiple_ranges: bool = True,
    ):
        if not network:
            raise exceptions.NetworkMappingValidationError(
                "network is a mandatory argument"
            )
        self.__network = network
        self.__ranges: typing.List[HostNetworkRange] = []
        self.__parse_raw(raw_config, allow_multiple_ranges)

    def __parse_raw(
        self, raw_definition: typing.Dict[str, typing.Any], allow_multiple_ranges: bool
    ):
        field_name = (
            self.__FIELD_RANGES if allow_multiple_ranges else self.__FIELD_SINGLE_RANGE
        )

        raw_ranges = _validate_parse_field_type(
            field_name,
            raw_definition,
            list if allow_multiple_ranges else dict,
            parent_name=self.__network.name,
            parent_type="network",
            mandatory=False,
        )

        ranges_list = raw_ranges if isinstance(raw_ranges, list) else [raw_ranges]
        self.__ranges = [
            HostNetworkRange.from_raw(self.__network.network, range_data)
            for range_data in ranges_list
        ]

    def get_ranges(self) -> typing.List[HostNetworkRange]:
        return self.__ranges

    def __hash__(self) -> int:
        return hash(
            (
                self.__network.name,
                tuple(self.__ranges),
            )
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, SubnetBasedNetworkToolDefinition):
            return False

        return (
            self.__network.name == other.__network.name
            and self.__ranges == other.__ranges
        )


class MultusNetworkDefinition(SubnetBasedNetworkToolDefinition):
    def __init__(
        self,
        network: NetworkDefinition,
        raw_config: typing.Dict[str, typing.Any],
    ):
        super().__init__(network, raw_config, allow_multiple_ranges=False)


class MetallbNetworkDefinition(SubnetBasedNetworkToolDefinition):
    def __init__(
        self,
        network: NetworkDefinition,
        raw_config: typing.Dict[str, typing.Any],
    ):
        super().__init__(network, raw_config)


class NetconfigNetworkDefinition(SubnetBasedNetworkToolDefinition):
    def __init__(
        self,
        network: NetworkDefinition,
        raw_config: typing.Dict[str, typing.Any],
    ):
        super().__init__(network, raw_config)


class NetworkDefinition:
    __OBJECT_TYPE_NAME = "network"

    __FIELD_NETWORK = "network"
    __FIELD_MTU = "mtu"
    __FIELD_VLAN_ID = "vlan"

    __FIELD_TOOLS = "tools"
    __FIELD_TOOLS_MULTUS = "multus"
    __FIELD_TOOLS_METALLB = "metallb"
    __FIELD_TOOLS_NETCONFIG = "netconfig"

    def __init__(self, name: str, raw_definition: typing.Dict[str, typing.Any]) -> None:
        if not name:
            raise exceptions.NetworkMappingValidationError(
                "name is a mandatory argument"
            )
        self.__name = name

        self.__vlan = None
        self.__mtu = None
        self.__network = None
        self.__multus_config: typing.Union[MultusNetworkDefinition, None] = None
        self.__metallb_config: typing.Union[MetallbNetworkDefinition, None] = None
        self.__netconfig_config: typing.Union[NetconfigNetworkDefinition, None] = None
        self.__parse_raw(raw_definition)

    @property
    def name(self) -> str:
        return self.__name

    @property
    def vlan(self) -> typing.Union[int, None]:
        return self.__vlan

    @property
    def mtu(self) -> typing.Union[int, None]:
        return self.__mtu

    @property
    def multus_config(self) -> typing.Union[MultusNetworkDefinition, None]:
        return self.__multus_config

    @property
    def metallb_config(self) -> typing.Union[MetallbNetworkDefinition, None]:
        return self.__metallb_config

    @property
    def netconfig_config(self) -> typing.Union[NetconfigNetworkDefinition, None]:
        return self.__netconfig_config

    @property
    def network(self) -> typing.Union[ipaddress.IPv4Network, ipaddress.IPv6Network]:
        return self.__network

    def __parse_raw(self, raw_definition: typing.Dict[str, typing.Any]):
        ip_net_str = raw_definition.get(self.__FIELD_NETWORK, None)
        _raise_missing_field(
            ip_net_str,
            self.__FIELD_NETWORK,
            parent_name=self.__name,
            parent_type=self.__OBJECT_TYPE_NAME,
        )

        try:
            self.__network = ipaddress.ip_network(ip_net_str)
        except ValueError as err:
            raise exceptions.NetworkMappingValidationError(
                "Invalid network value",
                field=self.__FIELD_NETWORK,
                invalid_value=ip_net_str,
            ) from err

        self.__mtu = _validate_parse_int(
            self.__FIELD_MTU,
            raw_definition,
            parent_name=self.__name,
            parent_type=self.__OBJECT_TYPE_NAME,
            min_value=1,
        )
        self.__vlan = _validate_parse_int(
            self.__FIELD_VLAN_ID,
            raw_definition,
            parent_name=self.__name,
            parent_type=self.__OBJECT_TYPE_NAME,
            min_value=1,
            max_value=4094,
        )

        self.__parse_tools(raw_definition)

    def __parse_tools(self, raw_definition: typing.Dict[str, typing.Any]):
        tools_raw_config = _validate_parse_field_type(
            self.__FIELD_TOOLS,
            raw_definition,
            dict,
            parent_name=self.__name,
            parent_type=self.__OBJECT_TYPE_NAME,
            mandatory=False,
        )
        if tools_raw_config:
            self.__parse_tool_multus(tools_raw_config)
            self.__parse_tool_metallb(tools_raw_config)
            self.__parse_tool_netconfig(tools_raw_config)
            self.__check_tools_ranges()

    def __get_tools_ranges(self):
        result = []
        if self.__multus_config:
            result.extend(self.__multus_config.get_ranges())
        if self.__metallb_config:
            result.extend(self.__metallb_config.get_ranges())
        if self.__netconfig_config:
            result.extend(self.__netconfig_config.get_ranges())
        return result

    def __check_tools_ranges(self):
        ranges = self.__get_tools_ranges()
        if len(ranges) > 1:
            (
                colliding_item1,
                colliding_item2,
            ) = check_host_network_ranges_collisions(ranges)
            if colliding_item1:
                raise exceptions.HostNetworkRangeCollisionValidationError(
                    f"{self.__name} contains tools with ranges that collides",
                    range_1=colliding_item1,
                    range_2=colliding_item2,
                )

    def __parse_tool_multus(self, raw_definition: typing.Dict[str, typing.Any]):
        multus_raw_config = _validate_parse_field_type(
            self.__FIELD_TOOLS_MULTUS,
            raw_definition,
            dict,
            parent_name=self.__name,
            parent_type=self.__OBJECT_TYPE_NAME,
            mandatory=False,
        )
        if multus_raw_config:
            self.__multus_config = MultusNetworkDefinition(self, multus_raw_config)

    def __parse_tool_metallb(self, raw_definition: typing.Dict[str, typing.Any]):
        metallb_raw_config = _validate_parse_field_type(
            self.__FIELD_TOOLS_METALLB,
            raw_definition,
            dict,
            parent_name=self.__name,
            parent_type=self.__OBJECT_TYPE_NAME,
            mandatory=False,
        )
        if metallb_raw_config:
            self.__metallb_config = MetallbNetworkDefinition(self, metallb_raw_config)

    def __parse_tool_netconfig(self, raw_definition: typing.Dict[str, typing.Any]):
        netconfig_raw_config = _validate_parse_field_type(
            self.__FIELD_TOOLS_NETCONFIG,
            raw_definition,
            dict,
            parent_name=self.__name,
            parent_type=self.__OBJECT_TYPE_NAME,
            mandatory=False,
        )
        if netconfig_raw_config:
            self.__netconfig_config = NetconfigNetworkDefinition(
                self, netconfig_raw_config
            )

    def __hash__(self) -> int:
        return hash(
            (
                self.__network,
                self.__name,
                self.__mtu,
                self.__vlan,
                self.__multus_config,
                self.__netconfig_config,
                self.__metallb_config,
            )
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, NetworkDefinition):
            return False

        return (
            self.__network == other.__network
            and self.__name == other.__name
            and self.__mtu == other.__mtu
            and self.__vlan == other.__vlan
            and self.__multus_config == other.__multus_config
            and self.__netconfig_config == other.__netconfig_config
            and self.__metallb_config == other.__metallb_config
        )


@dataclasses.dataclass
class GroupTemplateNetworkDefinition:
    network: NetworkDefinition
    range: HostNetworkRange = None
    skip_nm_configuration: bool = False

    def __hash__(self) -> int:
        return hash((self.network, self.range, self.skip_nm_configuration))


class GroupTemplateDefinition:
    __OBJECT_TYPE_NAME = "host-template"
    __FIELD_SKIP_NM = "skip-nm-configuration"
    __FIELD_NETWORKS = "networks"
    __FIELD_NETWORK_TEMPLATE = "network-template"
    __FIELD_NETWORK_SKIP_NM = "skip-nm-configuration"
    __FIELD_NETWORK_RANGE = "range"
    __FIELD_NETWORK_RANGE_START = "start"
    __FIELD_NETWORK_RANGE_LENGTH = "length"

    def __init__(
        self,
        group_name,
        raw_definition: typing.Dict[str, typing.Any],
        network_definitions: typing.Dict[str, NetworkDefinition],
    ):
        if not group_name:
            raise exceptions.NetworkMappingValidationError(
                "group_name is a mandatory argument"
            )
        self.__group_name = group_name

        self.__skip_nm_configuration: bool = False
        self.__groups_networks_definitions = {}
        self.__parse_raw(raw_definition, network_definitions)

    @property
    def networks(self) -> typing.Dict[str, GroupTemplateNetworkDefinition]:
        return self.__groups_networks_definitions

    @property
    def skip_nm_configuration(self) -> bool:
        return self.__skip_nm_configuration

    @property
    def group_name(self) -> str:
        return self.__group_name

    def __parse_raw(
        self,
        raw_definition: typing.Dict[str, typing.Any],
        network_definitions: typing.Dict[str, NetworkDefinition],
    ):
        self.__skip_nm_configuration = bool(
            raw_definition.get(self.__FIELD_SKIP_NM, False)
        )

        networks = _validate_parse_field_type(
            self.__FIELD_NETWORKS,
            raw_definition,
            dict,
            parent_name=self.__group_name,
            parent_type=self.__OBJECT_TYPE_NAME,
            mandatory=False,
        )
        if networks:
            network_template_raw = (
                _validate_parse_field_type(
                    self.__FIELD_NETWORK_TEMPLATE,
                    raw_definition,
                    dict,
                    parent_name=self.__group_name,
                    parent_type=self.__OBJECT_TYPE_NAME,
                    mandatory=False,
                )
                or {}
            )

            for network_name, network_data in networks.items():
                self.__parse_raw_net(
                    network_name,
                    network_data,
                    network_template_raw,
                    network_definitions,
                )

    def __parse_raw_net(
        self,
        network_name: str,
        network_data: typing.Dict[str, typing.Any],
        network_template_raw: typing.Dict[str, typing.Any],
        network_definitions: typing.Dict[str, NetworkDefinition],
    ):
        network_definition = network_definitions.get(network_name, None)
        if not network_definition:
            raise exceptions.NetworkMappingValidationError(
                f"{self.__group_name} template points "
                f"to the non-existing network {network_name}",
                invalid_value=network_name,
            )

        templated_net_data = {**network_template_raw, **network_data}
        network_range_raw = templated_net_data.get(self.__FIELD_NETWORK_RANGE, None)
        network_range = None
        if network_range_raw:
            network_range = HostNetworkRange.from_raw(
                network_definition.network, network_range_raw
            )

        skip_nm_configuration = bool(
            templated_net_data.get(self.__FIELD_NETWORK_SKIP_NM, False)
        )

        self.__groups_networks_definitions[
            network_name
        ] = GroupTemplateNetworkDefinition(
            network_definitions[network_name],
            range=network_range,
            skip_nm_configuration=skip_nm_configuration,
        )

    def __hash__(self) -> int:
        return hash(
            (
                frozenset(self.__groups_networks_definitions.items()),
                self.__group_name,
                self.__skip_nm_configuration,
            )
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, GroupTemplateDefinition):
            return False

        return (
            self.__group_name == other.__group_name
            and self.__groups_networks_definitions
            == other.__groups_networks_definitions
            and self.__skip_nm_configuration == other.__skip_nm_configuration
        )


@dataclasses.dataclass
class InstanceNetworkDefinition:
    network: NetworkDefinition
    ip: typing.Union[ipaddress.IPv4Address, ipaddress.IPv6Address] = None
    skip_nm_configuration: bool = False

    def __hash__(self) -> int:
        return hash((self.network, self.ip, self.skip_nm_configuration))


class InstanceDefinition:
    __FIELD_SKIP_NM = "skip-nm-configuration"
    __FIELD_NETWORKS = "networks"
    __FIELD_NETWORKS_IP = "ip"
    __FIELD_NETWORK_SKIP_NM = "skip-nm-configuration"

    def __init__(
        self,
        name: str,
        raw_definition: typing.Dict[str, typing.Any],
        network_definitions: typing.Dict[str, NetworkDefinition],
    ):
        if not name:
            raise exceptions.NetworkMappingValidationError(
                "name is a mandatory argument"
            )
        self.__name = name
        self.__skip_nm_configuration: bool = False
        self.__instances_network_definitions = {}
        self.__parse_raw(raw_definition, network_definitions)

    @property
    def networks(self) -> typing.Dict[str, InstanceNetworkDefinition]:
        return self.__instances_network_definitions

    @property
    def skip_nm_configuration(self) -> bool:
        return self.__skip_nm_configuration

    @property
    def name(self) -> str:
        return self.__name

    def __parse_raw(
        self,
        raw_definition: typing.Dict[str, typing.Any],
        network_definitions: typing.Dict[str, NetworkDefinition],
    ):
        self.__skip_nm_configuration = bool(
            raw_definition.get(self.__FIELD_SKIP_NM, False)
        )
        networks = raw_definition.get(self.__FIELD_NETWORKS, {})
        if not isinstance(networks, dict):
            raise exceptions.NetworkMappingValidationError(
                f"Field '{self.__FIELD_NETWORKS}' must be a dictionary",
                field=self.__FIELD_NETWORKS,
            )

        for network_name, network_data in networks.items():
            self.__parse_raw_net(network_name, network_data, network_definitions)

    def __parse_raw_net(
        self,
        network_name: str,
        network_data: typing.Dict[str, typing.Any],
        network_definitions: typing.Dict[str, NetworkDefinition],
    ):
        network_definition = network_definitions.get(network_name, None)
        if not network_definition:
            raise exceptions.NetworkMappingValidationError(
                f"{self.__name} instance points to the "
                f"non-existing network {network_name}",
                invalid_value=network_name,
            )
        instance_net_ip_raw = network_data.get(self.__FIELD_NETWORKS_IP, None)
        net_ip = None
        if instance_net_ip_raw:
            try:
                net_ip = ipaddress.ip_address(instance_net_ip_raw)
                if net_ip not in network_definition.network:
                    raise exceptions.NetworkMappingValidationError(
                        f"{self.__name} instance given IP is not "
                        f"part of the linked network {network_name} "
                        f"({network_definition.network})",
                        invalid_value=instance_net_ip_raw,
                        field=self.__FIELD_NETWORKS_IP,
                    )
            except ValueError as err:
                raise exceptions.NetworkMappingValidationError(
                    f"{instance_net_ip_raw} instance IP for {network_name} "
                    "network is not a valid IP",
                    invalid_value=str(instance_net_ip_raw),
                    field=self.__FIELD_NETWORKS_IP,
                ) from err

        skip_nm_configuration = bool(
            network_data.get(self.__FIELD_NETWORK_SKIP_NM, False)
        )

        self.__instances_network_definitions[network_name] = InstanceNetworkDefinition(
            network_definition,
            ip=net_ip,
            skip_nm_configuration=skip_nm_configuration,
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.__name,
                frozenset(self.__instances_network_definitions.items()),
                self.__skip_nm_configuration,
            )
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, InstanceDefinition):
            return False

        return (
            self.__name == other.__name
            and self.__instances_network_definitions
            == other.__instances_network_definitions
            and self.__skip_nm_configuration == other.__skip_nm_configuration
        )


class NetworkingDefinition:
    __FIELD_NETWORKS = "networks"
    __FIELD_GROUP_TEMPLATES = "group-templates"
    __FIELD_INSTANCES = "instances"

    def __init__(self, raw_definition: typing.Dict[str, typing.Any]):
        self.__networks: typing.Dict[str, NetworkDefinition] = {}
        self.__group_templates: typing.Dict[str, GroupTemplateDefinition] = {}
        self.__instances = {}

        self.__parse_raw(raw_definition)

    @property
    def networks(self) -> typing.Dict[str, NetworkDefinition]:
        return self.__networks

    @property
    def group_templates(self) -> typing.Dict[str, GroupTemplateDefinition]:
        return self.__group_templates

    @property
    def instances(self) -> typing.Dict[str, InstanceDefinition]:
        return self.__instances

    def __parse_raw(self, raw_definition: typing.Dict[str, typing.Any]):
        networks_raw = (
            _validate_parse_field_type(
                self.__FIELD_NETWORKS,
                raw_definition,
                dict,
                mandatory=False,
            )
            or {}
        )

        group_templates_raw = (
            _validate_parse_field_type(
                self.__FIELD_GROUP_TEMPLATES,
                raw_definition,
                dict,
                mandatory=False,
            )
            or {}
        )

        instances_raw = (
            _validate_parse_field_type(
                self.__FIELD_INSTANCES,
                raw_definition,
                dict,
                mandatory=False,
            )
            or {}
        )

        self.__networks = {
            net_name: NetworkDefinition(net_name, net_raw)
            for net_name, net_raw in networks_raw.items()
        }
        self.__group_templates = {
            group_name: GroupTemplateDefinition(group_name, group_raw, self.__networks)
            for group_name, group_raw in group_templates_raw.items()
        }
        self.__instances = {
            instance_name: InstanceDefinition(
                instance_name, instance_raw, self.__networks
            )
            for instance_name, instance_raw in instances_raw.items()
        }

        self.__check_overlapping_ranges()

    def __check_overlapping_ranges(self):
        ranges_by_net: typing.Dict[str, typing.List[HostNetworkRange]] = {}
        for group_definition in self.__group_templates.values():
            for net_name, group_net_def in group_definition.networks.items():
                if net_name not in ranges_by_net:
                    ranges_by_net[net_name] = []
                if group_net_def.range:
                    ranges_by_net[net_name].append(group_net_def.range)

        for net_name, net_ranges in ranges_by_net.items():
            if len(net_ranges) < 2:
                continue

            (
                colliding_item1,
                colliding_item2,
            ) = check_host_network_ranges_collisions(net_ranges)
            if colliding_item1:
                raise exceptions.HostNetworkRangeCollisionValidationError(
                    f"{net_name} contains ranges that collides",
                    range_1=colliding_item1,
                    range_2=colliding_item2,
                )

    def __hash__(self) -> int:
        return hash(
            (
                frozenset(self.__networks.items()),
                frozenset(self.__group_templates.items()),
                frozenset(self.__instances.items()),
            )
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, NetworkingDefinition):
            return False

        return (
            self.__networks == other.__networks
            and self.__instances == other.__instances
            and self.__group_templates == other.__group_templates
        )