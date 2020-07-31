import React, { FunctionComponent, ChangeEvent } from 'react';

interface SelectBoxFilterProps {
    label: string;
    options: {value: string, label: string}[];
    value: string|null;
    onChange(value: string): void;
}

const SelectBoxFilter: FunctionComponent<SelectBoxFilterProps> = ({label, options, value, onChange}) => {
    const onSelectChange = (e: ChangeEvent<HTMLSelectElement>) => {
        e.preventDefault();
        onChange(e.target.value);
    };

    const emptyOption = {
        value: '',
        label: '---------',
    };

    return (
        <label>
            {label}
            <select value={value || ""} onChange={onSelectChange}>
                {[emptyOption].concat(options).map(({value, label}) => {
                    return <option value={value}>{label}</option>
                })}
            </select>
        </label>
    );
};

export default SelectBoxFilter;
